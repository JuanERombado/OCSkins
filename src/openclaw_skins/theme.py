from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    font_family: str = "Segoe UI"
    panel_background_rgba: str = "rgba(13, 19, 28, 215)"
    panel_border_rgba: str = "rgba(255, 235, 210, 110)"
    text: str = "#F7F2EA"
    text_muted: str = "#D5CDC1"
    accent: str = "#F08F4B"
    accent_hover: str = "#FDB271"
    success: str = "#51B36E"
    danger: str = "#D26452"
    warning: str = "#F3C563"


def build_stylesheet(theme: ThemeTokens) -> str:
    return f"""
    QWidget#RootWindow {{
        background: transparent;
        color: {theme.text};
        font-family: "{theme.font_family}";
    }}
    QFrame#OverlayPanel {{
        background: {theme.panel_background_rgba};
        border: 1px solid {theme.panel_border_rgba};
        border-radius: 18px;
    }}
    QLabel#PanelTitle {{
        font-size: 14pt;
        font-weight: 600;
    }}
    QLabel#StatusLabel {{
        font-size: 12pt;
        font-weight: 600;
    }}
    QLabel#DetailLabel {{
        color: {theme.text_muted};
        font-size: 9pt;
    }}
    QLabel#FeedbackLabel {{
        color: {theme.warning};
        font-size: 9pt;
    }}
    QPushButton {{
        background: rgba(255, 255, 255, 22);
        color: {theme.text};
        border: 1px solid rgba(255, 255, 255, 40);
        border-radius: 10px;
        padding: 7px 12px;
    }}
    QPushButton:hover {{
        border-color: {theme.accent_hover};
    }}
    QPushButton:disabled {{
        color: rgba(255, 255, 255, 110);
        border-color: rgba(255, 255, 255, 26);
    }}
    QCheckBox {{
        color: {theme.text_muted};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid rgba(255, 255, 255, 55);
        background: rgba(255, 255, 255, 18);
    }}
    QCheckBox::indicator:checked {{
        background: {theme.accent};
        border-color: {theme.accent_hover};
    }}
    """
