"""通过截图 OCR 和 PyAutoGUI 修改企业微信当前聊天联系人的备注名。

公开入口：change_wecom_remark(original_remark, new_remark, ...)

该模块不使用 UIA，也不使用固定屏幕坐标。所有界面控件都通过 OCR 文字及
相对位置定位，并在保存前后分别核验备注，避免误改联系人。
"""

from __future__ import annotations

import argparse
import ctypes
import difflib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol, Sequence


# 让窗口坐标、鼠标坐标和截图像素在高 DPI 显示器上保持一致。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except (AttributeError, OSError):
    pass

import pyautogui
import pygetwindow
import pyperclip
from PIL import Image, ImageGrab, ImageStat


class RemarkChangeError(RuntimeError):
    """备注修改失败，且程序已在危险动作前停止。"""


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class OCRItem:
    text: str
    confidence: float
    box: Box


@dataclass(frozen=True)
class WindowRect:
    left: int
    top: int
    width: int
    height: int


@dataclass
class ChangeResult:
    success: bool
    original_remark: str
    new_remark: str
    edit_strategy: str
    evidence_files: list[str]
    message: str


class OCREngine(Protocol):
    def read(self, image: Image.Image) -> list[OCRItem]: ...


class RapidOCREngine:
    """RapidOCR 2.x/3.x 的轻量兼容封装。模型在首次运行时初始化。"""

    def __init__(self, min_confidence: float = 0.60) -> None:
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise RemarkChangeError(
                "缺少 RapidOCR，请先运行：pip install -r requirements.txt"
            ) from exc
        self._engine = RapidOCR()
        self._min_confidence = min_confidence

    def read(self, image: Image.Image) -> list[OCRItem]:
        import numpy as np

        output = self._engine(np.asarray(image.convert("RGB")))
        boxes = getattr(output, "boxes", None)
        texts = getattr(output, "txts", None)
        scores = getattr(output, "scores", None)

        # 兼容旧版返回 (result, elapsed)，其中 result 为 [box, text, score]。
        if boxes is None and isinstance(output, tuple) and output:
            legacy = output[0] or []
            boxes = [row[0] for row in legacy]
            texts = [row[1] for row in legacy]
            scores = [row[2] for row in legacy]

        if boxes is None or texts is None or scores is None:
            return []

        items: list[OCRItem] = []
        for points, text, score in zip(boxes, texts, scores):
            confidence = float(score)
            if confidence < self._min_confidence:
                continue
            xs = [int(round(float(point[0]))) for point in points]
            ys = [int(round(float(point[1]))) for point in points]
            items.append(
                OCRItem(
                    text=str(text),
                    confidence=confidence,
                    box=Box(min(xs), min(ys), max(xs), max(ys)),
                )
            )
        return items


@dataclass
class AutomationConfig:
    window_title: str = "企业微信"
    timeout_seconds: float = 8.0
    poll_seconds: float = 0.45
    action_pause_seconds: float = 0.35
    edit_strategy: Literal["select_all", "prefix_delete"] = "select_all"
    restore_clipboard: bool = True
    restore_window_position: bool = True
    move_offscreen_window_to_primary: bool = True
    dry_run: bool = False
    evidence_dir: Path = Path("wecom_remark_evidence")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def _contains(item: OCRItem, expected: str) -> bool:
    return _normalized(expected) in _normalized(item.text)


def _exact(item: OCRItem, expected: str) -> bool:
    return _normalized(item.text) == _normalized(expected)


def _similarity(actual: str, expected: str) -> float:
    actual_value = _normalized(actual)
    expected_value = _normalized(expected)
    if not actual_value or not expected_value:
        return 0.0
    if len(actual_value) <= len(expected_value):
        return difflib.SequenceMatcher(None, actual_value, expected_value).ratio()
    # OCR 常把“备注名”和“@微信”合并；取与期望等长的最佳子串比较。
    width = len(expected_value)
    return max(
        difflib.SequenceMatcher(
            None, actual_value[start : start + width], expected_value
        ).ratio()
        for start in range(len(actual_value) - width + 1)
    )


def _field_value_matches(actual: str, expected: str) -> bool:
    """匹配输入框完整值，避免把新值误认成较长旧值的近似结果。"""
    actual_value = _normalized(actual)
    expected_value = _normalized(expected)
    # 输入框 OCR 可以错一个字符，但不能缺少整段后缀。
    allowed_length_error = max(1, round(len(expected_value) * 0.12))
    if abs(len(actual_value) - len(expected_value)) > allowed_length_error:
        return False
    return _similarity(actual_value, expected_value) >= 0.84


def _is_blue_selected(image: Image.Image, item: OCRItem) -> bool:
    """检查 OCR 文字左侧是否为企业微信的蓝色选中行背景。"""
    rgb = image.convert("RGB")
    y = max(0, min(rgb.height - 1, item.box.center[1]))
    sample_xs = {
        max(0, item.box.left - 70),
        max(0, item.box.left - 35),
        max(0, min(rgb.width - 1, item.box.center[0])),
    }
    blue_votes = 0
    for x in sample_xs:
        red, green, blue = rgb.getpixel((x, y))
        if blue > red + 55 and blue > green + 35 and blue > 150:
            blue_votes += 1
    return blue_votes >= 1


def choose_selected_conversation(
    items: Sequence[OCRItem], expected: str, image: Image.Image
) -> OCRItem:
    """确认左侧蓝色选中行就是待修改联系人。"""
    candidates = [
        item
        for item in items
        if _similarity(item.text, expected) >= 0.84
        and item.box.center[0] < image.width * 0.36
        and _is_blue_selected(image, item)
    ]
    if len(candidates) != 1:
        raise RemarkChangeError(
            f"左侧蓝色选中会话与原备注不唯一匹配：实际 {len(candidates)} 个"
        )
    return candidates[0]


def choose_header_name(
    items: Sequence[OCRItem], expected: str, width: int, height: int
) -> OCRItem:
    """选择聊天区顶部名称；允许 OCR 出现一个近似字符错误。"""
    candidates = [
        item
        for item in items
        if _similarity(item.text, expected) >= 0.84
        and item.box.center[0] > width * 0.34
        and item.box.center[1] < height * 0.16
    ]
    if len(candidates) != 1:
        raise RemarkChangeError(
            f"顶部备注名定位不唯一：期望 1 个，实际 {len(candidates)} 个"
        )
    return candidates[0]


def choose_description_content(items: Sequence[OCRItem]) -> OCRItem:
    labels = [item for item in items if _exact(item, "描述")]
    if len(labels) != 1:
        raise RemarkChangeError(f"“描述”标签定位不唯一：实际 {len(labels)} 个")
    label = labels[0]
    candidates = [
        item
        for item in items
        if item.box.left > label.box.right
        and abs(item.box.center[1] - label.box.center[1])
        <= max(30, label.box.height * 2)
        and not _exact(item, "描述")
    ]
    if not candidates:
        raise RemarkChangeError("未在“描述”右侧找到可点击的文本内容")
    # 选与标签同行且文字最长的候选；描述通常会被 OCR 分成一至两行。
    return min(
        candidates,
        key=lambda item: (
            abs(item.box.center[1] - label.box.center[1]),
            -len(_normalized(item.text)),
        ),
    )


def choose_remark_input_text(
    items: Sequence[OCRItem], original_remark: str
) -> tuple[OCRItem, OCRItem]:
    labels = [item for item in items if _exact(item, "备注名")]
    if len(labels) != 1:
        raise RemarkChangeError(f"“备注名”标签定位不唯一：实际 {len(labels)} 个")
    label = labels[0]
    candidates = [
        item
        for item in items
        if _field_value_matches(item.text, original_remark)
        and item.box.top > label.box.bottom
        and item.box.top - label.box.bottom < max(100, label.box.height * 5)
        and item.box.left >= label.box.left - 30
    ]
    if len(candidates) != 1:
        raise RemarkChangeError(
            f"备注输入框中的原备注定位不唯一：实际 {len(candidates)} 个"
        )
    return label, candidates[0]


def choose_edited_remark_input_text(
    items: Sequence[OCRItem], new_remark: str, original_remark: str
) -> tuple[OCRItem, OCRItem]:
    """在备注名标签下核验输入框已包含完整新值，且完整旧值已消失。"""
    labels = [item for item in items if _exact(item, "备注名")]
    if len(labels) != 1:
        raise RemarkChangeError(f"“备注名”标签定位不唯一：实际 {len(labels)} 个")
    label = labels[0]
    field_items = [
        item
        for item in items
        if item.box.top > label.box.bottom
        and item.box.top - label.box.bottom < max(100, label.box.height * 5)
        and item.box.left >= label.box.left - 30
    ]
    new_candidates = [
        item for item in field_items if _field_value_matches(item.text, new_remark)
    ]
    old_candidates = [
        item for item in field_items if _field_value_matches(item.text, original_remark)
    ]
    if len(new_candidates) != 1 or old_candidates:
        raise RemarkChangeError(
            "备注输入框核验失败："
            f"新备注匹配 {len(new_candidates)} 个，原备注残留 {len(old_candidates)} 个"
        )
    return label, new_candidates[0]


class WeComRemarkChanger:
    def __init__(
        self,
        ocr: OCREngine | None = None,
        config: AutomationConfig | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.ocr = ocr or RapidOCREngine()
        self.config = config or AutomationConfig()
        self.sleep = sleep
        self.evidence_files: list[str] = []
        self.config.evidence_dir.mkdir(parents=True, exist_ok=True)
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = self.config.action_pause_seconds

    def _find_window(self):
        matches = [
            window
            for window in pygetwindow.getWindowsWithTitle(self.config.window_title)
            if window.title == self.config.window_title
        ]
        if len(matches) != 1:
            raise RemarkChangeError(
                f"企业微信窗口定位不唯一：期望 1 个，实际 {len(matches)} 个"
            )
        window = matches[0]
        if window.isMinimized:
            window.restore()
        window.activate()
        self.sleep(0.6)
        return window

    @staticmethod
    def _rect(window) -> WindowRect:
        return WindowRect(window.left, window.top, window.width, window.height)

    def _capture(self, window, step: str) -> tuple[Image.Image, list[OCRItem]]:
        rect = self._rect(window)
        screen_w, screen_h = pyautogui.size()
        on_primary = (
            rect.left >= 0
            and rect.top >= 0
            and rect.left + rect.width <= screen_w
            and rect.top + rect.height <= screen_h
        )
        if on_primary:
            image = pyautogui.screenshot(
                region=(rect.left, rect.top, rect.width, rect.height)
            )
        else:
            image = ImageGrab.grab(
                bbox=(
                    rect.left,
                    rect.top,
                    rect.left + rect.width,
                    rect.top + rect.height,
                ),
                all_screens=True,
            )
            # 某些 PyAutoGUI/Pillow 组合对负坐标返回黑图，调用方可选择移窗重试。
            if sum(ImageStat.Stat(image.convert("L")).mean) < 3:
                raise RemarkChangeError("窗口截图为黑图，可能位于不受支持的负坐标显示器")

        path = self.config.evidence_dir / f"{len(self.evidence_files) + 1:02d}_{step}.png"
        image.save(path)
        self.evidence_files.append(str(path.resolve()))
        return image, self.ocr.read(image)

    def _wait_for(
        self,
        window,
        step: str,
        predicate: Callable[[list[OCRItem], Image.Image], object],
    ):
        deadline = time.monotonic() + self.config.timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                image, items = self._capture(window, step)
                result = predicate(items, image)
                if result:
                    return result, image, items
            except RemarkChangeError as exc:
                last_error = exc
            self.sleep(self.config.poll_seconds)
        detail = f"；最后错误：{last_error}" if last_error else ""
        raise RemarkChangeError(f"等待界面状态超时：{step}{detail}")

    @staticmethod
    def _click(window, point: tuple[int, int]) -> None:
        pyautogui.click(window.left + point[0], window.top + point[1])

    @staticmethod
    def _paste_text(text: str) -> None:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")

    def _edit_remark(self, original_remark: str, new_remark: str) -> None:
        if self.config.edit_strategy == "select_all":
            pyautogui.hotkey("ctrl", "a")
            self._paste_text(new_remark)
            return

        # 用户建议的策略：光标移到最前面，插入新值，再删除后面的旧值。
        pyautogui.press("home")
        self._paste_text(new_remark)
        pyautogui.press("delete", presses=len(original_remark), interval=0.02)

    def _prepare_window_for_capture(self, window) -> tuple[int, int, bool]:
        original_position = (window.left, window.top)
        moved = False
        if self.config.move_offscreen_window_to_primary and (
            window.left < 0
            or window.top < 0
            or window.left + window.width > pyautogui.size().width
            or window.top + window.height > pyautogui.size().height
        ):
            x = max(0, (pyautogui.size().width - window.width) // 2)
            y = max(0, (pyautogui.size().height - window.height) // 2)
            window.moveTo(x, y)
            window.activate()
            self.sleep(0.6)
            moved = True
        return original_position[0], original_position[1], moved

    def change_remark(self, original_remark: str, new_remark: str) -> ChangeResult:
        if not original_remark or not new_remark:
            raise ValueError("原备注和新备注均不能为空")
        if original_remark == new_remark:
            raise ValueError("原备注和新备注不能相同")

        window = self._find_window()
        old_left, old_top, moved = self._prepare_window_for_capture(window)
        old_clipboard = pyperclip.paste() if self.config.restore_clipboard else None

        try:
            def verified_chat(items: list[OCRItem], image: Image.Image):
                choose_selected_conversation(items, original_remark, image)
                return choose_header_name(
                    items, original_remark, image.width, image.height
                )

            header, _, _ = self._wait_for(
                window,
                "chat_verified",
                verified_chat,
            )
            self._click(window, header.box.center)

            description, _, _ = self._wait_for(
                window,
                "contact_card",
                lambda items, _image: choose_description_content(items),
            )
            self._click(window, description.box.center)

            field_info, _, _ = self._wait_for(
                window,
                "edit_dialog",
                lambda items, _image: choose_remark_input_text(items, original_remark),
            )
            label, original_text = field_info
            self._click(window, original_text.box.center)
            self._edit_remark(original_remark, new_remark)

            def edited_value_is_correct(items: list[OCRItem], _image: Image.Image):
                choose_edited_remark_input_text(
                    items, new_remark, original_remark
                )
                return True

            self._wait_for(
                window, "before_save_verified", edited_value_is_correct
            )

            if self.config.dry_run:
                return ChangeResult(
                    success=True,
                    original_remark=original_remark,
                    new_remark=new_remark,
                    edit_strategy=self.config.edit_strategy,
                    evidence_files=self.evidence_files.copy(),
                    message="演练完成：新备注已填入并核验，未按回车保存。",
                )

            pyautogui.press("enter")

            def saved_value_is_correct(
                current_items: list[OCRItem], current_image: Image.Image
            ):
                choose_selected_conversation(
                    current_items, new_remark, current_image
                )
                return choose_header_name(
                    current_items,
                    new_remark,
                    current_image.width,
                    current_image.height,
                )

            self._wait_for(
                window,
                "after_save_verified",
                saved_value_is_correct,
            )
            return ChangeResult(
                success=True,
                original_remark=original_remark,
                new_remark=new_remark,
                edit_strategy=self.config.edit_strategy,
                evidence_files=self.evidence_files.copy(),
                message="备注修改成功，并已通过聊天顶部名称核验。",
            )
        finally:
            if self.config.restore_clipboard and old_clipboard is not None:
                pyperclip.copy(old_clipboard)
            if moved and self.config.restore_window_position:
                window.moveTo(old_left, old_top)


def change_wecom_remark(
    original_remark: str,
    new_remark: str,
    *,
    edit_strategy: Literal["select_all", "prefix_delete"] = "select_all",
    dry_run: bool = False,
    evidence_dir: str | Path = "wecom_remark_evidence",
) -> ChangeResult:
    """修改企业微信当前聊天联系人的备注名。

    输入示例：("py175示例学员/新生", "py175示例学员")
    返回 ChangeResult；失败时抛出 RemarkChangeError，并保留过程截图。
    """
    config = AutomationConfig(
        edit_strategy=edit_strategy,
        dry_run=dry_run,
        evidence_dir=Path(evidence_dir),
    )
    return WeComRemarkChanger(config=config).change_remark(
        original_remark, new_remark
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="修改企业微信当前聊天联系人的备注")
    parser.add_argument("original_remark", help="修改前的完整备注")
    parser.add_argument("new_remark", help="修改后的完整备注")
    parser.add_argument(
        "--edit-strategy",
        choices=("select_all", "prefix_delete"),
        default="select_all",
        help="select_all 更稳；prefix_delete 使用 Home + 新备注 + Delete×旧备注长度",
    )
    parser.add_argument("--dry-run", action="store_true", help="填入并核验，但不保存")
    parser.add_argument(
        "--evidence-dir", default="wecom_remark_evidence", help="过程截图目录"
    )
    args = parser.parse_args()
    try:
        result = change_wecom_remark(
            args.original_remark,
            args.new_remark,
            edit_strategy=args.edit_strategy,
            dry_run=args.dry_run,
            evidence_dir=args.evidence_dir,
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
