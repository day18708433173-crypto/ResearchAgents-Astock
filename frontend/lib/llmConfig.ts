export interface UserLlmConfig {
  apiKey: string;
  baseUrl: string;
  model: string;
}

export const USER_LLM_CONFIG_KEY = "jingheng_user_llm_config";

export const LLM_PROVIDER_PRESETS = [
  { label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-v4-flash" },
  { label: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { label: "通义千问", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { label: "智谱 GLM", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash" },
] as const;

/** DeepSeek 官方兼容两种 base_url，匹配预设时视为同一 Provider */
function isSameBaseUrl(a: string, b: string): boolean {
  const norm = (url: string) => url.trim().replace(/\/+$/, "");
  const na = norm(a);
  const nb = norm(b);
  if (na === nb) return true;
  const deepseekBases = ["https://api.deepseek.com", "https://api.deepseek.com/v1"];
  return deepseekBases.includes(na) && deepseekBases.includes(nb);
}

export function findLlmProviderByBaseUrl(baseUrl: string) {
  return LLM_PROVIDER_PRESETS.find((item) => isSameBaseUrl(item.baseUrl, baseUrl));
}

export function findLlmProviderPreset(config: Pick<UserLlmConfig, "baseUrl" | "model">) {
  return LLM_PROVIDER_PRESETS.find(
    (item) => isSameBaseUrl(item.baseUrl, config.baseUrl) && item.model === config.model
  );
}

export function resolveLlmProviderLabel(config: Pick<UserLlmConfig, "baseUrl">): string {
  return findLlmProviderByBaseUrl(config.baseUrl)?.label || "自定义";
}

export function normalizeUserLlmConfig(config: Partial<UserLlmConfig>): UserLlmConfig {
  return {
    apiKey: (config.apiKey || "").trim(),
    baseUrl: (config.baseUrl || "").trim().replace(/\/+$/, ""),
    model: (config.model || "").trim(),
  };
}

export function isUserLlmConfigComplete(config: Partial<UserLlmConfig> | null | undefined): boolean {
  if (!config) return false;
  const normalized = normalizeUserLlmConfig(config);
  return Boolean(normalized.apiKey && normalized.baseUrl && normalized.model);
}

export function loadUserLlmConfig(): UserLlmConfig | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_LLM_CONFIG_KEY);
    if (!raw) return null;
    return normalizeUserLlmConfig(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function saveUserLlmConfig(config: UserLlmConfig): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(USER_LLM_CONFIG_KEY, JSON.stringify(normalizeUserLlmConfig(config)));
}

export function clearUserLlmConfig(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(USER_LLM_CONFIG_KEY);
}

export function buildUserLlmHeaders(): HeadersInit {
  const config = loadUserLlmConfig();
  if (!isUserLlmConfigComplete(config)) return {};
  const normalized = normalizeUserLlmConfig(config || {});
  return {
    "x-jh-llm-api-key": normalized.apiKey,
    "x-jh-llm-base-url": normalized.baseUrl,
    "x-jh-llm-model": normalized.model,
  };
}
