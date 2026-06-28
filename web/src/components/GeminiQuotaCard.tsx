/**
 * Gemini 配额状态卡片。
 * 通过 babel-bridge /quota 代理接口展示每个模型的可用状态、成功次数、429次数、重置时间。
 * 植入 UsagePage 的 UsageOmniConfig 下方。
 */

import { useTranslation } from "react-i18next";
import { getBabelQuota } from "@/api";
import { useAsync } from "@/hooks/useAsync";
import type { BabelModelQuota } from "@/lib/types";

function relativeTime(iso: string): string {
  const d = new Date(iso);
  const diff = Math.round((d.getTime() - Date.now()) / 1000);
  if (diff < 0) {
    const abs = Math.abs(diff);
    if (abs < 60) return `${abs}秒前`;
    if (abs < 3600) return `${Math.round(abs / 60)}分钟前`;
    return `${Math.round(abs / 3600)}小时前`;
  }
  if (diff < 60) return `${diff}秒后`;
  if (diff < 3600) return `${Math.round(diff / 60)}分钟后`;
  return `${Math.round(diff / 3600)}小时后`;
}

function ModelRow({ name, q }: { name: string; q: BabelModelQuota }) {
  const { t } = useTranslation();
  const shortName = name.replace("gemini-", "").replace("-preview", "★");
  return (
    <div className="flex items-center gap-3 py-2 border-b border-border last:border-0">
      {/* 状态点 */}
      <span
        className={`shrink-0 w-2 h-2 rounded-full ${q.available ? "bg-green-500" : "bg-red-500"}`}
        aria-hidden
      />
      {/* 模型名 */}
      <span className="flex-1 text-sm font-mono text-text-primary truncate" title={name}>
        {shortName}
      </span>
      {/* 成功/429 */}
      <span className="text-xs text-text-secondary whitespace-nowrap">
        {t("usage.geminiQuotaSuccess", { n: q.total_success })}
        {q.total_429s > 0 && (
          <span className="ml-2 text-amber-500">
            {t("usage.geminiQuota429", { n: q.total_429s })}
          </span>
        )}
      </span>
      {/* 状态/重置 */}
      <span
        className={`text-xs font-medium whitespace-nowrap ${
          q.available ? "text-green-600 dark:text-green-400" : "text-red-500"
        }`}
      >
        {q.available
          ? t("usage.geminiQuotaAvailable")
          : q.resets_at
            ? t("usage.geminiQuotaResetsAt", { time: relativeTime(q.resets_at) })
            : t("usage.geminiQuotaExhausted")}
      </span>
    </div>
  );
}

export function GeminiQuotaCard() {
  const { t } = useTranslation();
  const { data, loading, error } = useAsync(getBabelQuota, [], {
    errorLabel: t("usage.loadError"),
  });

  return (
    <section className="rounded-xl bg-bg-secondary border border-border shadow-sm p-5 md:p-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-section-title">{t("usage.geminiQuotaTitle")}</h2>
        {data?.updated_at && (
          <span className="text-xs text-text-secondary">
            {t("usage.geminiQuotaUpdated", { time: relativeTime(data.updated_at) })}
          </span>
        )}
      </div>

      {loading && (
        <div className="py-4 text-center text-text-secondary text-sm">{t("usage.loading")}</div>
      )}

      {!loading && (error || !data) && (
        <div className="py-4 text-center text-text-secondary text-sm">
          {t("usage.geminiQuotaUnavailable")}
        </div>
      )}

      {data && Object.keys(data.models).length === 0 && (
        <div className="py-4 text-center text-text-secondary text-sm">
          {t("usage.geminiQuotaNoData")}
        </div>
      )}

      {data && Object.keys(data.models).length > 0 && (
        <div>
          {Object.entries(data.models)
            .sort(([, a], [, b]) => {
              // available first, then by total_success desc
              if (a.available !== b.available) return a.available ? -1 : 1;
              return b.total_success - a.total_success;
            })
            .map(([name, q]) => (
              <ModelRow key={name} name={name} q={q} />
            ))}
          <p className="mt-2 text-xs text-text-secondary">
            重置周期 {data.reset_cycle_hours}h
          </p>
        </div>
      )}
    </section>
  );
}
