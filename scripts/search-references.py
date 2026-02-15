#!/usr/bin/env python3
"""
甄嬛传 References 多关键词搜索脚本
用法：
    python search-references.py 关键词1 关键词2 ...

选项：
    --dir       指定 References 目录路径（默认：./References）
    --mode      匹配模式：any（含任一关键词）/ all（同时含所有关键词），默认 any
    --context   每处命中前后显示的行数，默认 2
    --files     只搜索指定文件（逗号分隔，如 episodes-01-10,characters）
    --no-color  关闭颜色高亮

示例：
    python search-references.py 欢宜香 麝香
    python search-references.py 甄嬛 果郡王 --mode all --context 3
    python search-references.py 皇后 宜修 --files characters,episodes-61-70
"""

import argparse
import os
import re
import sys
from pathlib import Path


# ── ANSI 颜色 ────────────────────────────────────────────────────────────────

class Colors:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    RED     = "\033[91m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    GREEN   = "\033[92m"
    GREY    = "\033[90m"
    MAGENTA = "\033[95m"

def colorize(text: str, color: str, use_color: bool) -> str:
    return f"{color}{text}{Colors.RESET}" if use_color else text


# ── 文件过滤 ─────────────────────────────────────────────────────────────────

# 文件友好别名（用于 --files 参数和展示）
FILE_ALIASES = {
    "characters":      "characters.md",
    "episode-guide":   "episode-guide.md",
    "events":          "events.md",
    "episodes-01-10":  "episodes-01-10.md",
    "episodes-11-20":  "episodes-11-20.md",
    "episodes-21-30":  "episodes-21-30.md",
    "episodes-31-40":  "episodes-31-40.md",
    "episodes-41-50":  "episodes-41-50.md",
    "episodes-51-60":  "episodes-51-60.md",
    "episodes-61-70":  "episodes-61-70.md",
    "episodes-71-76":  "episodes-71-76.md",
}

def get_target_files(ref_dir: Path, files_filter: list[str] | None) -> list[Path]:
    """返回要搜索的文件列表，保持固定顺序。"""
    all_files = sorted(ref_dir.glob("*.md"))

    if not files_filter:
        return all_files

    selected = set()
    for token in files_filter:
        token = token.strip()
        # 先按别名匹配
        if token in FILE_ALIASES:
            selected.add(FILE_ALIASES[token])
        else:
            # 尝试模糊匹配文件名
            for f in all_files:
                if token.lower() in f.name.lower():
                    selected.add(f.name)

    return [f for f in all_files if f.name in selected]


# ── 搜索核心 ─────────────────────────────────────────────────────────────────

def build_pattern(keyword: str) -> re.Pattern:
    """编译关键词为正则，支持普通字符串（自动转义）。"""
    return re.compile(re.escape(keyword))


def highlight_keywords(line: str, patterns: list[re.Pattern], use_color: bool) -> str:
    """在一行中对所有关键词做高亮标记（不重叠）。"""
    if not use_color:
        return line

    # 收集所有匹配区间，按起始位置排序
    spans = []
    for pat in patterns:
        for m in pat.finditer(line):
            spans.append((m.start(), m.end(), m.group()))

    if not spans:
        return line

    spans.sort(key=lambda x: x[0])

    # 合并重叠区间并重建字符串
    result = []
    prev_end = 0
    for start, end, matched in spans:
        if start < prev_end:
            continue
        result.append(line[prev_end:start])
        result.append(colorize(matched, Colors.RED + Colors.BOLD, True))
        prev_end = end
    result.append(line[prev_end:])
    return "".join(result)


def search_file(
    filepath: Path,
    patterns: list[re.Pattern],
    keywords: list[str],
    mode: str,
    context_lines: int,
    use_color: bool,
) -> list[dict]:
    """
    在单个文件中搜索，返回命中记录列表。
    每条记录包含：line_num, line, context_before, context_after, matched_keywords
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[警告] 无法读取 {filepath.name}: {e}", file=sys.stderr)
        return []

    lines = text.splitlines()
    hits = []

    for i, line in enumerate(lines):
        matched_kws = [kw for pat, kw in zip(patterns, keywords) if pat.search(line)]

        if mode == "all" and len(matched_kws) < len(keywords):
            continue
        if mode == "any" and not matched_kws:
            continue

        before = lines[max(0, i - context_lines): i]
        after  = lines[i + 1: i + 1 + context_lines]

        hits.append({
            "line_num":        i + 1,
            "line":            line,
            "context_before":  before,
            "context_after":   after,
            "matched_keywords": matched_kws,
        })

    return hits


# ── 输出格式化 ────────────────────────────────────────────────────────────────

def print_results(
    results: dict[str, list[dict]],
    patterns: list[re.Pattern],
    keywords: list[str],
    use_color: bool,
    mode: str,
) -> None:
    total_files  = sum(1 for hits in results.values() if hits)
    total_hits   = sum(len(hits) for hits in results.values())

    if total_hits == 0:
        msg = "未找到任何匹配结果。"
        print(colorize(msg, Colors.YELLOW, use_color))
        return

    # ── 摘要栏 ──────────────────────────────────────────────────────────────
    mode_label = "同时含" if mode == "all" else "含任一"
    kw_display = " + ".join(
        colorize(f"「{kw}」", Colors.CYAN + Colors.BOLD, use_color)
        for kw in keywords
    )
    summary = (
        f"\n搜索关键词：{kw_display}  "
        f"模式：{mode_label}  |  "
        f"命中：{colorize(str(total_hits), Colors.GREEN + Colors.BOLD, use_color)} 处  "
        f"涉及 {colorize(str(total_files), Colors.GREEN + Colors.BOLD, use_color)} 个文件\n"
    )
    print(summary)

    # ── 按文件输出 ───────────────────────────────────────────────────────────
    for filename, hits in results.items():
        if not hits:
            continue

        # 文件标题
        file_header = colorize(
            f"{'━' * 60}\n📄  {filename}  [{len(hits)} 处命中]\n{'━' * 60}",
            Colors.MAGENTA + Colors.BOLD, use_color
        )
        print(file_header)

        for hit in hits:
            line_num = hit["line_num"]
            line     = hit["line"]

            # 上下文行（灰色）
            for ctx_line in hit["context_before"]:
                print(colorize(f"  {ctx_line}", Colors.GREY, use_color))

            # 命中行（行号 + 高亮）
            highlighted = highlight_keywords(line, patterns, use_color)
            line_label  = colorize(f"→ L{line_num:<5}", Colors.YELLOW + Colors.BOLD, use_color)
            print(f"{line_label} {highlighted}")

            for ctx_line in hit["context_after"]:
                print(colorize(f"  {ctx_line}", Colors.GREY, use_color))

            print()  # 命中间空行

    # ── 文件命中数一览 ───────────────────────────────────────────────────────
    print(colorize("─" * 60, Colors.GREY, use_color))
    print(colorize("命中统计：", Colors.BOLD, use_color))
    for filename, hits in results.items():
        if hits:
            bar = "█" * min(len(hits), 40)
            print(f"  {filename:<30} {colorize(bar, Colors.GREEN, use_color)}  {len(hits)}")
    print()


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="甄嬛传 References 多关键词搜索",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "keywords",
        nargs="+",
        help="搜索关键词（一个或多个）",
    )
    parser.add_argument(
        "--dir",
        default="./References",
        help="References 目录路径（默认：./References）",
    )
    parser.add_argument(
        "--mode",
        choices=["any", "all"],
        default="any",
        help="any=含任一关键词（默认），all=同时含所有关键词",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=2,
        metavar="N",
        help="每处命中前后显示的行数（默认：2）",
    )
    parser.add_argument(
        "--files",
        default=None,
        help="只搜索指定文件（逗号分隔，如 characters,episodes-01-10）",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="关闭颜色高亮（写入文件时建议开启）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    use_color = not args.no_color and sys.stdout.isatty()
    ref_dir   = Path(args.dir)

    # ── 目录检查 ─────────────────────────────────────────────────────────────
    if not ref_dir.exists():
        print(
            colorize(f"[错误] 目录不存在：{ref_dir}", Colors.RED, use_color),
            file=sys.stderr,
        )
        sys.exit(1)

    # ── 文件列表 ─────────────────────────────────────────────────────────────
    files_filter = [f.strip() for f in args.files.split(",")] if args.files else None
    target_files = get_target_files(ref_dir, files_filter)

    if not target_files:
        print(
            colorize("[警告] 未找到任何 .md 文件，请检查目录或 --files 参数。", Colors.YELLOW, use_color),
            file=sys.stderr,
        )
        sys.exit(1)

    # ── 编译关键词 ────────────────────────────────────────────────────────────
    keywords = args.keywords
    patterns = [build_pattern(kw) for kw in keywords]

    # ── 逐文件搜索 ────────────────────────────────────────────────────────────
    results: dict[str, list[dict]] = {}
    for filepath in target_files:
        hits = search_file(
            filepath, patterns, keywords,
            mode=args.mode,
            context_lines=args.context,
            use_color=use_color,
        )
        results[filepath.name] = hits

    # ── 输出 ─────────────────────────────────────────────────────────────────
    print_results(results, patterns, keywords, use_color, args.mode)


if __name__ == "__main__":
    main()
