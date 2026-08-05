from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {count}")
    file_path.write_text(text.replace(old, new, 1))


def replace_count(path: str, old: str, new: str, expected: int) -> None:
    file_path = Path(path)
    text = file_path.read_text()
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} exact matches, found {count}")
    file_path.write_text(text.replace(old, new))


def write_file(path: str, content: str) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content.rstrip() + "\n")


HELPER = """
import { DEFAULT_ACCOUNT_ID } from "./resolve.js";

const QQBOT_DOCS_URL = "https://docs.openclaw.ai/channels/qqbot";
const QQBOT_OPEN_PLATFORM_URL = "https://q.qq.com/";

export function qqbotAuthGuidance(): string {
  return `Check the QQBot account appId and clientSecret (or clientSecretFile) in OpenClaw and verify the credentials in QQ Open Platform at ${QQBOT_OPEN_PLATFORM_URL}. See ${QQBOT_DOCS_URL}`;
}

export function qqbotNetworkGuidance(): string {
  return `Check network connectivity and DNS, and verify the server IP whitelist in QQ Open Platform at ${QQBOT_OPEN_PLATFORM_URL}. See ${QQBOT_DOCS_URL}`;
}

export function qqbotApiGuidance(httpStatus: number): string {
  return httpStatus === 401
    ? qqbotAuthGuidance()
    : `See ${QQBOT_DOCS_URL} for QQBot API troubleshooting`;
}

export function qqbotNotConfiguredMessage(accountId: string): string {
  const guidance =
    accountId === DEFAULT_ACCOUNT_ID
      ? `Set channels.qqbot.appId and clientSecret (or clientSecretFile), or set QQBOT_APP_ID and QQBOT_CLIENT_SECRET. See ${QQBOT_DOCS_URL}`
      : `Set channels.qqbot.accounts.${accountId}.appId and clientSecret (or clientSecretFile). See ${QQBOT_DOCS_URL}`;
  return `QQBot not configured (missing appId or clientSecret). ${guidance}`;
}

export function qqbotTokenFailureMessage(detail: string): string {
  return `Failed to get QQBot access_token. ${qqbotAuthGuidance()}. Open platform response: ${detail}`;
}
"""

HELPER_TEST = """
import { describe, expect, it } from "vitest";
import {
  qqbotApiGuidance,
  qqbotAuthGuidance,
  qqbotNetworkGuidance,
  qqbotNotConfiguredMessage,
} from "./setup-guidance.js";

describe("QQBot setup guidance", () => {
  it("offers default-account config and environment variables", () => {
    const message = qqbotNotConfiguredMessage("default");

    expect(message).toContain("channels.qqbot.appId");
    expect(message).toContain("QQBOT_APP_ID and QQBOT_CLIENT_SECRET");
    expect(message).toContain("https://docs.openclaw.ai/channels/qqbot");
  });

  it("directs named accounts to account-scoped config without default-only environment variables", () => {
    const message = qqbotNotConfiguredMessage("operations");

    expect(message).toContain("channels.qqbot.accounts.operations.appId");
    expect(message).toContain("clientSecret (or clientSecretFile)");
    expect(message).not.toContain("QQBOT_APP_ID");
    expect(message).not.toContain("QQBOT_CLIENT_SECRET");
  });

  it("keeps authentication guidance account-neutral", () => {
    const message = qqbotAuthGuidance();

    expect(message).toContain("QQBot account appId");
    expect(message).toContain("https://q.qq.com/");
    expect(message).not.toContain("QQBOT_APP_ID");
    expect(message).not.toContain("QQBOT_CLIENT_SECRET");
  });

  it("keeps network guidance cause-specific", () => {
    const message = qqbotNetworkGuidance();

    expect(message).toContain("network connectivity and DNS");
    expect(message).toContain("server IP whitelist");
    expect(message).not.toContain("appId");
    expect(message).not.toContain("clientSecret");
  });

  it("uses credential guidance only for HTTP 401 API failures", () => {
    expect(qqbotApiGuidance(401)).toContain("appId and clientSecret");
    expect(qqbotApiGuidance(403)).not.toContain("appId");
    expect(qqbotApiGuidance(429)).not.toContain("appId");
  });
});
"""

GATEWAY_TEST = """
import { describe, expect, it } from "vitest";
import { startGateway, type CoreGatewayContext } from "./gateway.js";

function makeContext(accountId: string): CoreGatewayContext {
  return {
    account: {
      accountId,
      appId: "",
      clientSecret: "",
      markdownSupport: false,
      config: {},
    },
    adapters: {
      commands: {},
      outboundAudio: {},
    },
  } as unknown as CoreGatewayContext;
}

describe("QQBot gateway configuration guidance", () => {
  it("shows default-account recovery paths from the real gateway entry point", async () => {
    await expect(startGateway(makeContext("default"))).rejects.toThrow(
      /channels\.qqbot\.appId.*QQBOT_APP_ID and QQBOT_CLIENT_SECRET/,
    );
  });

  it("shows account-scoped recovery without default-only env vars", async () => {
    let error: unknown;
    try {
      await startGateway(makeContext("operations"));
    } catch (caught) {
      error = caught;
    }

    const message = error instanceof Error ? error.message : String(error);
    expect(message).toContain("channels.qqbot.accounts.operations.appId");
    expect(message).not.toContain("QQBOT_APP_ID");
    expect(message).not.toContain("QQBOT_CLIENT_SECRET");
  });
});
"""

OUTBOUND_TEST = """
import { describe, expect, it } from "vitest";
import type { GatewayAccount } from "../types.js";
import { sendMedia, sendText } from "./outbound.js";

function makeAccount(accountId: string): GatewayAccount {
  return {
    accountId,
    appId: "",
    clientSecret: "",
    markdownSupport: false,
    config: {},
  };
}

describe("QQBot outbound configuration guidance", () => {
  it("returns default-account recovery paths from sendText", async () => {
    const result = await sendText({
      account: makeAccount("default"),
      to: "user-openid",
      text: "hello",
    });

    expect(result.error).toContain("channels.qqbot.appId");
    expect(result.error).toContain("QQBOT_APP_ID and QQBOT_CLIENT_SECRET");
  });

  it("returns named-account recovery paths from sendMedia", async () => {
    const result = await sendMedia({
      account: makeAccount("operations"),
      accountId: "operations",
      to: "user-openid",
      text: "",
      mediaUrl: "https://example.com/image.png",
    });

    expect(result.error).toContain("channels.qqbot.accounts.operations.appId");
    expect(result.error).not.toContain("QQBOT_APP_ID");
    expect(result.error).not.toContain("QQBOT_CLIENT_SECRET");
  });
});
"""

write_file("extensions/qqbot/src/engine/config/setup-guidance.ts", HELPER)
write_file("extensions/qqbot/src/engine/config/setup-guidance.test.ts", HELPER_TEST)
write_file("extensions/qqbot/src/engine/gateway/gateway.config.test.ts", GATEWAY_TEST)
write_file("extensions/qqbot/src/engine/messaging/outbound-config.test.ts", OUTBOUND_TEST)

replace_once(
    "extensions/qqbot/src/engine/gateway/gateway.ts",
    'import { resolveGroupCommandLevelFromAccountConfig } from "../config/group.js";\nimport type { HistoryEntry } from "../group/history.js";',
    'import { resolveGroupCommandLevelFromAccountConfig } from "../config/group.js";\nimport { qqbotNotConfiguredMessage } from "../config/setup-guidance.js";\nimport type { HistoryEntry } from "../group/history.js";',
)
replace_once(
    "extensions/qqbot/src/engine/gateway/gateway.ts",
    'throw new Error("QQBot not configured (missing appId or clientSecret)");',
    "throw new Error(qqbotNotConfiguredMessage(account.accountId));",
)

replace_once(
    "extensions/qqbot/src/engine/messaging/outbound.ts",
    'import { truncateUtf16Safe } from "openclaw/plugin-sdk/text-utility-runtime";\nimport type { GatewayAccount } from "../types.js";',
    'import { truncateUtf16Safe } from "openclaw/plugin-sdk/text-utility-runtime";\nimport { qqbotNotConfiguredMessage } from "../config/setup-guidance.js";\nimport type { GatewayAccount } from "../types.js";',
)
replace_count(
    "extensions/qqbot/src/engine/messaging/outbound.ts",
    'return { channel: "qqbot", error: "QQBot not configured (missing appId or clientSecret)" };',
    'return { channel: "qqbot", error: qqbotNotConfiguredMessage(account.accountId) };',
    2,
)

replace_once(
    "extensions/qqbot/src/engine/api/token.ts",
    'import { fetchWithSsrFGuard, type SsrFPolicy } from "openclaw/plugin-sdk/ssrf-runtime";\nimport type { EngineLogger } from "../types.js";',
    'import { fetchWithSsrFGuard, type SsrFPolicy } from "openclaw/plugin-sdk/ssrf-runtime";\nimport { qqbotNetworkGuidance, qqbotTokenFailureMessage } from "../config/setup-guidance.js";\nimport type { EngineLogger } from "../types.js";',
)
replace_once(
    "extensions/qqbot/src/engine/api/token.ts",
    'throw new Error(`Network error getting access_token: ${formatErrorMessage(err)}`, {\n        cause: err,\n      });',
    'throw new Error(\n        `Network error getting access_token: ${formatErrorMessage(err)}. ${qqbotNetworkGuidance()}`,\n        { cause: err },\n      );',
)
replace_once(
    "extensions/qqbot/src/engine/api/token.ts",
    'throw new Error(`Failed to get access_token: ${JSON.stringify(data)}`);',
    "throw new Error(qqbotTokenFailureMessage(JSON.stringify(data)));",
)

replace_once(
    "extensions/qqbot/src/engine/api/api-client.ts",
    'import { truncateUtf16Safe } from "openclaw/plugin-sdk/text-utility-runtime";\nimport { ApiError, type ApiClientConfig, type EngineLogger } from "../types.js";',
    'import { truncateUtf16Safe } from "openclaw/plugin-sdk/text-utility-runtime";\nimport { qqbotApiGuidance, qqbotNetworkGuidance } from "../config/setup-guidance.js";\nimport { ApiError, type ApiClientConfig, type EngineLogger } from "../types.js";',
)
replace_once(
    "extensions/qqbot/src/engine/api/api-client.ts",
    'throw new ApiError(`Network error [${path}]: ${formatErrorMessage(err)}`, 0, path);',
    'throw new ApiError(\n        `Network error [${path}]: ${formatErrorMessage(err)}. ${qqbotNetworkGuidance()}`,\n        0,\n        path,\n      );',
)
replace_once(
    "extensions/qqbot/src/engine/api/api-client.ts",
    '`API Error [${path}]: ${error.message ?? rawBody}`',
    '`API Error [${path}]: ${error.message ?? rawBody}. ${qqbotApiGuidance(res.status)}`',
)

TOKEN_TEST = """
  it("adds account-neutral credential guidance when the token endpoint omits access_token", async () => {
    const release = mockGuardedTokenResponse('{"code":4001,"message":"invalid app secret"}', {
      status: 200,
      headers: { "content-type": "application/json" },
    });

    let error: unknown;
    try {
      await new TokenManager().getAccessToken("app-id", "secret");
    } catch (caught) {
      error = caught;
    }

    const message = error instanceof Error ? error.message : String(error);
    expect(message).toContain("Failed to get QQBot access_token");
    expect(message).toContain("QQBot account appId and clientSecret");
    expect(message).toContain("https://q.qq.com/");
    expect(message).toContain('{"code":4001,"message":"invalid app secret"}');
    expect(message).not.toContain("QQBOT_APP_ID");
    expect(release).toHaveBeenCalledTimes(1);
  });

"""
replace_once(
    "extensions/qqbot/src/engine/api/token.test.ts",
    '  it("bounds access token responses without using response.text()", async () => {',
    TOKEN_TEST + '  it("bounds access token responses without using response.text()", async () => {',
)
replace_once(
    "extensions/qqbot/src/engine/api/token.test.ts",
    'expect(timeoutError.message).toBe("Network error getting access_token: request timed out");',
    'expect(timeoutError.message).toContain(\n      "Network error getting access_token: request timed out",\n    );\n    expect(timeoutError.message).toContain("Check network connectivity and DNS");\n    expect(timeoutError.message).toContain("server IP whitelist");\n    expect(timeoutError.message).not.toContain("appId");',
)

API_CLIENT_TESTS = """
  it("adds network and whitelist guidance to DNS failures without suggesting credentials", async () => {
    fetchWithSsrFGuardMock.mockRejectedValueOnce(
      new Error("getaddrinfo ENOTFOUND api.sgroup.qq.com"),
    );

    const client = new ApiClient({ baseUrl: "https://qqbot.test" });
    let error: unknown;
    try {
      await client.request("token-1", "GET", "/v2/users/@me");
    } catch (caught) {
      error = caught;
    }

    const message = error instanceof Error ? error.message : String(error);
    expect(message).toContain("Network error [/v2/users/@me]");
    expect(message).toContain("network connectivity and DNS");
    expect(message).toContain("server IP whitelist");
    expect(message).not.toContain("appId");
    expect(message).not.toContain("clientSecret");
  });

  it("adds credential guidance to structured HTTP 401 errors", async () => {
    const release = vi.fn(async () => {});
    fetchWithSsrFGuardMock.mockResolvedValueOnce({
      response: new Response('{"code":11241,"message":"invalid credentials"}', {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
      release,
    });

    const client = new ApiClient({ baseUrl: "https://qqbot.test" });
    let error: unknown;
    try {
      await client.request("token-1", "POST", "/v2/messages", { content: "hi" });
    } catch (caught) {
      error = caught;
    }

    const message = error instanceof Error ? error.message : String(error);
    expect(message).toContain("API Error [/v2/messages]: invalid credentials");
    expect(message).toContain("QQBot account appId and clientSecret");
    expect(message).toContain("https://q.qq.com/");
    expect(release).toHaveBeenCalledTimes(1);
  });

  it("keeps non-auth structured API guidance generic", async () => {
    const release = vi.fn(async () => {});
    fetchWithSsrFGuardMock.mockResolvedValueOnce({
      response: new Response('{"code":40034025,"message":"invalid event id"}', {
        status: 400,
        headers: { "content-type": "application/json" },
      }),
      release,
    });

    const client = new ApiClient({ baseUrl: "https://qqbot.test" });
    let error: unknown;
    try {
      await client.request("token-1", "POST", "/v2/messages", { content: "hi" });
    } catch (caught) {
      error = caught;
    }

    const message = error instanceof Error ? error.message : String(error);
    expect(message).toContain("API Error [/v2/messages]: invalid event id");
    expect(message).toContain("QQBot API troubleshooting");
    expect(message).not.toContain("appId");
    expect(message).not.toContain("clientSecret");
    expect(release).toHaveBeenCalledTimes(1);
  });

"""
replace_once(
    "extensions/qqbot/src/engine/api/api-client.test.ts",
    '  it("bounds successful response bodies without using response.text()", async () => {',
    API_CLIENT_TESTS + '  it("bounds successful response bodies without using response.text()", async () => {',
)

print("QQBot guidance patch applied with all exact-match guards satisfied")
