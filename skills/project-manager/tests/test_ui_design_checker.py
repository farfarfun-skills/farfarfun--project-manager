import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from scripts.ui_design_checker import analyze_ui_design


UI_HANDOFF = """# Game Catalog UI

## 1. 基本信息

- 功能名称：游戏目录
- 功能标识：game-catalog
- UI owner：UI设计师
- 关联 issue：PROJECT-1
- 状态：待评审
- 最后更新时间：2026-07-17
- PRD：docs/product/game-catalog/
- 架构与技术设计：docs/development/game-catalog/
- 测试用例：docs/testing/game-catalog/test-cases/
- 本地设计源文件：docs/design/game-catalog/assets/design-source.fig
- 页面截图目录：docs/design/game-catalog/screens/

## 2. 设计目标

- 本次解决的问题：展示游戏目录。
- 关键用户目标：快速找到游戏。
- 非目标：不改游戏详情。

## 3. 页面与入口范围

| 页面 | 入口 | 范围 |
| --- | --- | --- |
| 游戏目录 | 首页 | 范围内 |

## 4. 关键流程

1. 用户进入目录。
2. 用户浏览游戏。
3. 用户选择游戏。

## 5. 状态设计

| 状态 | 触发 | 表现 | 恢复动作 |
| --- | --- | --- | --- |
| 默认态 | 加载完成 | 展示列表 | 选择游戏 |
| 加载态 | 请求中 | 展示骨架 | 等待 |
| 错误态 | 请求失败 | 展示错误 | 重试 |

## 6. 组件与交互说明

| 组件 | 交互 | 约束 |
| --- | --- | --- |
| 游戏卡片 | 点击进入详情 | 保持卡片比例 |

## 7. 响应式与端差异

- Web：响应式网格。
- H5：无。
- App：无。
- 后台：无。

## 8. 视觉资源与设计稿链接

- 本地设计源文件：docs/design/game-catalog/assets/design-source.fig
- 页面截图目录：docs/design/game-catalog/screens/
- 导出资源目录：docs/design/game-catalog/exports/
- 图标资源目录：docs/design/game-catalog/assets/

## 9. 页面截图索引

| 页面 / 状态 | 文件 |
| --- | --- |
| 游戏目录 / 默认态 | page-game-catalog-default.png |

## 10. 验收重点

- 固定设计源文件与普通资源分别校验。
"""


class UiDesignCheckerTests(unittest.TestCase):
    def create_bundle(self, root: Path) -> Path:
        bundle = root / "docs/design/game-catalog"
        (bundle / "assets").mkdir(parents=True)
        (bundle / "screens").mkdir()
        (bundle / "exports").mkdir()
        (bundle / "001-overview.md").write_text(UI_HANDOFF, encoding="utf-8")
        (bundle / "assets/design-source.fig").touch()
        (bundle / "assets/asset-cover.png").touch()
        (bundle / "screens/page-game-catalog-default.png").touch()
        (bundle / "exports/asset-cover.png").touch()
        return bundle

    def test_fixed_design_source_is_not_reported_by_output_auto(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = self.create_bundle(Path(temp_dir))
            result = subprocess.run(
                [
                    sys.executable,
                    str(SKILL_ROOT / "scripts/ui_design_checker.py"),
                    "--ui",
                    str(bundle),
                    "--format",
                    "json",
                    "--output",
                    "auto",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(result.stdout)
            generated = Path(temp_dir) / "docs/review/ui-design/game-catalog.ui-design.generated.md"

            self.assertEqual("allow", report["normalized_decision"])
            self.assertTrue(generated.exists())
            self.assertNotIn("design-source.fig", json.dumps(report["findings"], ensure_ascii=False))

    def test_invalid_ordinary_asset_remains_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = self.create_bundle(Path(temp_dir))
            (bundle / "assets/logo.png").touch()

            report = analyze_ui_design(UI_HANDOFF, bundle)
            naming = [finding for finding in report["findings"] if finding["code"] == "assets.naming"]

            self.assertEqual(1, len(naming))
            self.assertIn("logo.png", naming[0]["detail"])
            self.assertNotIn("design-source.fig", naming[0]["detail"])


if __name__ == "__main__":
    unittest.main()
