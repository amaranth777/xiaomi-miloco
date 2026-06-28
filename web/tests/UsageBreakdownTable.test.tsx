// @vitest-environment happy-dom
/**
 * TDD: UsageBreakdownTable Gemini 视频/音频 token 展示
 * 当模型名含 "gemini" 且 video=0 且 audio=0 时，显示 "—" 而非 "0"
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
// 初始化 i18n（副作用），确保 useTranslation() 能取到译文
import "@/i18n";
import { UsageBreakdownTable } from "@/components/UsageBreakdownTable";
import type { UsageStats } from "@/lib/types";

function makeStats(model: string, video: number, audio: number): UsageStats {
  return {
    period: "today",
    total_tokens: 1000,
    calls: 10,
    totals: { input: 900, output: 100, cache: 0, video, audio },
    by_type: [],
    rows: [
      {
        model,
        type: "realtime",
        calls: 10,
        tokens: 1000,
        breakdown: { input: 900, output: 100, cache: 0, video, audio },
      },
    ],
    timeline: [],
  };
}

describe("UsageBreakdownTable", () => {
  it("shows — for video/audio when Gemini model and both are 0", () => {
    const stats = makeStats("gemini-2.0-flash", 0, 0);
    render(<UsageBreakdownTable stats={stats} />);
    // video 和 audio 列应该显示 "—" 而不是 "0"
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it("shows actual values when non-Gemini model with video tokens", () => {
    const stats = makeStats("claude-sonnet-4", 500, 200);
    render(<UsageBreakdownTable stats={stats} />);
    // 应该显示实际数值，不是 —
    expect(screen.queryAllByText("—").length).toBeLessThan(2);
  });

  it("shows actual values when Gemini but has non-zero video tokens", () => {
    // 如果 Gemini 某天真的有 video_tokens，也要正常显示
    const stats = makeStats("gemini-2.0-flash", 300, 0);
    render(<UsageBreakdownTable stats={stats} />);
    // video 有值时正常显示（300 tokens → humanTokens 格式化）
    expect(screen.queryByText(/300/)).toBeTruthy();
  });
});
