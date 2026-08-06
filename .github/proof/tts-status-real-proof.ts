import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { OpenClawConfig } from "openclaw/plugin-sdk/config-contracts";
import { startQaGatewayChild } from "../../extensions/qa-lab/src/gateway-child.ts";
import { startQaMockOpenAiServer } from "../../extensions/qa-lab/src/providers/mock-openai/server.ts";
import { GatewayClient, type GatewayClientOptions } from "../../src/gateway/client.ts";
import {
  GATEWAY_CLIENT_MODES,
  GATEWAY_CLIENT_NAMES,
  type GatewayClientMode,
  type GatewayClientName,
} from "../../src/utils/message-channel.ts";

const EXACT_HEAD = "38c125a6ebfecb3bdb8c72d8ec9a03eca7c7ac5f";
const PLUGIN_ID = "qa-slow-tts-status";
const PROVIDER_ID = "qa-slow-speech";
const BUSY_MS = 750;

async function createFixturePlugin(root: string) {
  const pluginDir = path.join(root, PLUGIN_ID);
  const eventPath = path.join(root, "provider-events.jsonl");
  await fs.mkdir(pluginDir, { recursive: true });
  await fs.writeFile(
    path.join(pluginDir, "openclaw.plugin.json"),
    `${JSON.stringify(
      {
        id: PLUGIN_ID,
        activation: { onStartup: true },
        configSchema: { type: "object", additionalProperties: false, properties: {} },
      },
      null,
      2,
    )}\n`,
  );
  await fs.writeFile(
    path.join(pluginDir, "index.js"),
    [
      'const fs = require("node:fs");',
      "",
      "function record(event) {",
      '  fs.appendFileSync(process.env.OPENCLAW_QA_TTS_STATUS_EVENTS, JSON.stringify(event) + "\\n");',
      "}",
      "",
      "module.exports = {",
      `  id: ${JSON.stringify(PLUGIN_ID)},`,
      "  register(api) {",
      "    api.registerSpeechProvider({",
      `      id: ${JSON.stringify(PROVIDER_ID)},`,
      '      label: "QA Slow Speech",',
      "      autoSelectOrder: 1,",
      "      isConfigured() {",
      "        const startedAt = Date.now();",
      '        record({ event: "isConfigured:start", at: startedAt });',
      `        const deadline = startedAt + Number(process.env.OPENCLAW_QA_TTS_STATUS_BUSY_MS || ${BUSY_MS});`,
      "        while (Date.now() < deadline) {}",
      "        const completedAt = Date.now();",
      '        record({ event: "isConfigured:end", at: completedAt });',
      "        return true;",
      "      },",
      "      async synthesize() {",
      '        throw new Error("QA status proof never synthesizes audio");',
      "      },",
      "    });",
      "  },",
      "};",
      "",
    ].join("\n"),
  );
  return { pluginDir, eventPath };
}

function withFixturePlugin(config: OpenClawConfig, pluginDir: string): OpenClawConfig {
  return {
    ...config,
    plugins: {
      ...config.plugins,
      enabled: true,
      allow: [...new Set([...(config.plugins?.allow ?? []), PLUGIN_ID])],
      load: {
        ...config.plugins?.load,
        paths: [...new Set([...(config.plugins?.load?.paths ?? []), pluginDir])],
      },
      entries: {
        ...config.plugins?.entries,
        [PLUGIN_ID]: { enabled: true },
      },
    },
    tts: {
      ...config.tts,
      provider: PROVIDER_ID,
    },
  };
}

async function connectGatewayClient(params: {
  clientName: GatewayClientName;
  mode: GatewayClientMode;
  token: string;
  url: string;
  onEvent?: GatewayClientOptions["onEvent"];
}) {
  const gatewayUrl = new URL(params.url);
  gatewayUrl.protocol = gatewayUrl.protocol === "wss:" ? "https:" : "http:";
  let resolveHello: (() => void) | undefined;
  let rejectHello: ((error: Error) => void) | undefined;
  const hello = new Promise<void>((resolve, reject) => {
    resolveHello = resolve;
    rejectHello = reject;
  });
  const client = new GatewayClient({
    url: params.url,
    origin: gatewayUrl.origin,
    token: params.token,
    clientName: params.clientName,
    mode: params.mode,
    role: "operator",
    scopes: ["operator.read", "operator.write", "operator.admin"],
    platform: "qa",
    requestTimeoutMs: 30_000,
    onEvent: params.onEvent,
    onHelloOk: () => resolveHello?.(),
    onConnectError: (error) => rejectHello?.(error),
    onClose: (code, reason) => rejectHello?.(new Error(`Gateway closed ${code}: ${reason}`)),
  });
  client.start();
  const timer = setTimeout(() => rejectHello?.(new Error("Gateway connect timeout")), 20_000);
  try {
    await hello;
  } catch (error) {
    client.stop();
    throw error;
  } finally {
    clearTimeout(timer);
  }
  return client;
}

type ProviderEvent = { event: string; at: number };

const fixtureRoot = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-tts-status-proof-"));
const fixture = await createFixturePlugin(fixtureRoot);
const mock = await startQaMockOpenAiServer();
let gateway: Awaited<ReturnType<typeof startQaGatewayChild>> | undefined;
let client: GatewayClient | undefined;
try {
  gateway = await startQaGatewayChild({
    repoRoot: process.cwd(),
    useRepoCli: true,
    providerBaseUrl: `${mock.baseUrl}/v1`,
    providerMode: "mock-openai",
    transportBaseUrl: "http://127.0.0.1",
    controlUiEnabled: true,
    runtimeEnvPatch: {
      OPENCLAW_QA_TTS_STATUS_EVENTS: fixture.eventPath,
      OPENCLAW_QA_TTS_STATUS_BUSY_MS: String(BUSY_MS),
      OPENCLAW_TTS_PREFS: path.join(fixtureRoot, "tts-prefs.json"),
    },
    mutateConfig: (config) => withFixturePlugin(config, fixture.pluginDir),
  });
  client = await connectGatewayClient({
    clientName: GATEWAY_CLIENT_NAMES.WEBCHAT_UI,
    mode: GATEWAY_CLIENT_MODES.WEBCHAT,
    token: gateway.token,
    url: gateway.wsUrl,
  });

  await client.request("last-heartbeat", {});
  await fs.writeFile(fixture.eventPath, "");

  const startedAt = Date.now();
  const completionOrder: string[] = [];
  let ttsCompletedAt = 0;
  let siblingCompletedAt = 0;

  const ttsRequest = client.request<Record<string, unknown>>("tts.status", {}).then((value) => {
    ttsCompletedAt = Date.now();
    completionOrder.push("tts.status");
    return value;
  });
  const siblingRequest = client
    .request<Record<string, unknown> | null>("last-heartbeat", {})
    .then((value) => {
      siblingCompletedAt = Date.now();
      completionOrder.push("last-heartbeat");
      return value;
    });

  const [ttsStatus, siblingResult] = await Promise.all([ttsRequest, siblingRequest]);
  const eventText = await fs.readFile(fixture.eventPath, "utf8");
  const providerEvents = eventText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as ProviderEvent);
  const starts = providerEvents.filter((event) => event.event === "isConfigured:start");
  const ends = providerEvents.filter((event) => event.event === "isConfigured:end");
  if (starts.length !== 1 || ends.length !== 1) {
    throw new Error(`expected one configured-state evaluation, got ${JSON.stringify(providerEvents)}`);
  }
  const providerStartAt = starts[0].at;
  const providerEndAt = ends[0].at;
  const providerState = Array.isArray(ttsStatus.providerStates)
    ? ttsStatus.providerStates.find(
        (value) =>
          value &&
          typeof value === "object" &&
          (value as Record<string, unknown>).id === PROVIDER_ID,
      )
    : undefined;

  const assertions = {
    siblingCompletedFirst: completionOrder[0] === "last-heartbeat",
    siblingCompletedBeforeSlowProviderFinished: siblingCompletedAt < providerEndAt,
    ttsCompletedAfterSlowProviderFinished: ttsCompletedAt >= providerEndAt,
    oneConfiguredStateEvaluation: starts.length === 1 && ends.length === 1,
    statusUsesFixtureProvider: ttsStatus.provider === PROVIDER_ID,
    providerStateReportedConfigured:
      providerState !== undefined && (providerState as Record<string, unknown>).configured === true,
  };
  if (Object.values(assertions).some((value) => !value)) {
    throw new Error(
      `TTS concurrency proof assertion failed: ${JSON.stringify({ assertions, completionOrder, providerEvents, ttsStatus, siblingResult })}`,
    );
  }

  const proof = {
    verdict: "pass",
    exactPrHead: EXACT_HEAD,
    transport: "real Gateway WebSocket RPC",
    requests: ["tts.status", "last-heartbeat"],
    fixture: {
      providerId: PROVIDER_ID,
      synchronousConfiguredDelayMs: providerEndAt - providerStartAt,
    },
    timingMs: {
      siblingCompleted: siblingCompletedAt - startedAt,
      providerStarted: providerStartAt - startedAt,
      providerCompleted: providerEndAt - startedAt,
      ttsCompleted: ttsCompletedAt - startedAt,
    },
    completionOrder,
    ttsStatus: {
      provider: ttsStatus.provider,
      fallbackProvider: ttsStatus.fallbackProvider,
      fixtureProviderState: providerState,
    },
    siblingResult,
    assertions,
  };
  await fs.writeFile("tts-status-real-gateway-proof.json", `${JSON.stringify(proof, null, 2)}\n`);
  console.log("TTS_STATUS_REAL_GATEWAY_PROOF");
  console.log(JSON.stringify(proof, null, 2));
} finally {
  client?.stop();
  await gateway?.stop().catch(() => undefined);
  await mock.stop();
  await fs.rm(fixtureRoot, { force: true, recursive: true });
}
