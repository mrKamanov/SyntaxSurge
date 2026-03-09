#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Modern Ember Glass Design for SyntaxSurge.
Высокая читаемость, теплые акценты и отсутствие визуального шума.
"""

# Геометрия (увеличим скругление для мягкости)
RADIUS_LG = 18
RADIUS_MD = 10
RADIUS_SM = 6

# Палитра "Industrial Dark"
DEFAULT_GLASS_OPACITY = 242            # 0–255, по умолчанию почти непрозрачный
ACCENT_COLOR = "#FFB86C"               # Мягкий янтарный (отлично виден)
ACCENT_HOVER = "#FFCC80"              # Светло-песочный при наведении
CHECK_ORANGE = "#FF9900"              # Ярко-оранжевый как кнопка «Старт распознавания»
ITEM_BG = "rgba(0, 0, 0, 0.3)"         # Темные подложки для инпутов
TEXT_BRIGHT = "#FFFFFF"                # Основной текст
TEXT_DIM = "rgba(200, 200, 210, 0.7)"  # Вторичный текст

# Стиль всплывающего списка QComboBox (для view().setStyleSheet на Windows)
COMBO_POPUP_STYLE = f"""
    QAbstractItemView {{
        background-color: rgba(24, 24, 28, 0.98);
        color: {TEXT_BRIGHT};
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: 4px;
        outline: none;
        selection-background-color: rgba(255, 184, 108, 0.35);
        selection-color: {TEXT_BRIGHT};
    }}
    QAbstractItemView::item {{ min-height: 28px; padding: 4px 10px; }}
    QAbstractItemView::item:hover {{ background-color: rgba(255, 255, 255, 0.08); }}
"""

def get_stylesheet(background_alpha: int = None) -> str:
    import os
    if background_alpha is None:
        background_alpha = DEFAULT_GLASS_OPACITY
    bg_main = f"rgba(24, 24, 28, {max(0, min(255, background_alpha))})"
    # Галочка в отмеченном чекбоксе рисуется в коде (gui.checkbox_style.CheckboxWithCheckStyle), не через image
    check_icon_url = ""
    return f"""
        /* 1. ГЛОБАЛЬНЫЕ НАСТРОЙКИ — УБИРАЕМ СКРЫТЫЕ ФОНЫ */
        QMainWindow, #centralContainer, #glassFrame, QScrollArea, #glassScroll, #glassScrollContent, QStackedWidget {{
            background: transparent;
            border: none;
        }}

        /* Основная подложка с эффектом дорогого стекла (только правая часть; слева — прозрачная полоска под кнопки) */
        #glassFrame {{
            background-color: {bg_main};
            border-radius: {RADIUS_LG}px;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}

        /* 2. ТИПОГРАФИКА */
        QLabel {{ 
            color: {TEXT_BRIGHT}; 
            font-family: 'Segoe UI', 'Inter', sans-serif;
            background: transparent;
        }}

        /* Заголовок в стиле бренда (двухцветный: основная часть + оранжевый акцент) */
        #glassTitleMain {{
            font-size: 30px;
            font-weight: 900;
            padding-top: 25px;
            padding-right: 0px;
            margin-right: 0px;
            color: #FFFFFF;
            letter-spacing: 2px;
        }}
        #glassTitleAccent {{
            font-size: 30px;
            font-weight: 900;
            padding: 6px 14px 6px 14px;
            margin-top: 19px;
            margin-left: 0px;
            color: #000000;
            background-color: #FF9900;
            border-radius: 6px;
            letter-spacing: 2px;
        }}
        #glassTitleSlash {{
            font-size: 30px;
            font-weight: 900;
            padding-top: 25px;
            margin-left: 6px;
            color: #FFFFFF;
            letter-spacing: 2px;
        }}

        #glassSectionTitle {{
            font-size: 12px;
            font-weight: 800;
            color: {TEXT_DIM};
            text-transform: uppercase;
            letter-spacing: 1.2px;
            margin-top: 15px;
            padding-bottom: 5px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}

        /* Подписи (в т.ч. у горячих клавиш) — всегда светлые, читаемые */
        #glassLabel {{
            color: {TEXT_BRIGHT};
            font-size: 13px;
        }}

        /* 3. ИНПУТЫ И ПОЛЯ */
        #glassInput {{
            background-color: {ITEM_BG};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: {RADIUS_MD}px;
            color: {TEXT_DIM};
            padding: 8px 12px;
            font-size: 14px;
        }}

        /* Поля горячих клавиш: одна рамка на фрейме, поле внутри — без своей рамки */
        #glassKeyEditFrame {{
            background-color: {ITEM_BG};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: {RADIUS_MD}px;
            min-width: 120px;
        }}
        #glassKeyEditFrame QLineEdit {{
            background: transparent;
            border: none;
            outline: none;
        }}
        #glassKeyEditFrame QLineEdit:focus {{
            border: none;
            outline: none;
        }}
        #glassKeyEditFrame QKeySequenceEdit {{
            background: transparent;
            border: none;
            outline: none;
            color: {TEXT_DIM};
            padding: 6px 10px;
            font-size: 14px;
            selection-color: {TEXT_BRIGHT};
            selection-background-color: rgba(255, 184, 108, 0.4);
        }}
        #glassKeyEditFrame QKeySequenceEdit:focus {{
            border: none;
            outline: none;
        }}
        /* Внутренний QLineEdit в QKeySequenceEdit — убираем синюю рамку фокуса и задаём цвет текста */
        #glassKeyEditFrame QKeySequenceEdit QLineEdit {{
            background: transparent;
            border: none;
            outline: none;
            color: {TEXT_DIM};
            selection-color: {TEXT_BRIGHT};
            selection-background-color: rgba(255, 184, 108, 0.4);
        }}
        #glassKeyEditFrame QKeySequenceEdit QLineEdit:focus {{
            border: none;
            outline: none;
        }}

        /* Комбобоксы (мышь/модификатор в настройках горячих клавиш, авторизация в API) */
        #glassCombo {{
            background-color: {ITEM_BG};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: {RADIUS_SM}px;
            color: {TEXT_DIM};
            padding: 4px 8px;
            font-size: 13px;
            min-height: 24px;
        }}
        /* Всплывающий список комбобокса — без белой рамки, в тон фона */
        QComboBox QAbstractItemView {{
            background-color: rgba(24, 24, 28, 0.98);
            color: {TEXT_BRIGHT};
            border: none;
            border-radius: {RADIUS_SM}px;
            padding: 4px;
            outline: none;
            selection-background-color: rgba(255, 184, 108, 0.35);
            selection-color: {TEXT_BRIGHT};
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 28px;
            padding: 4px 10px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: rgba(255, 255, 255, 0.08);
        }}

        /* Область ответа ИИ на главной — прокручивается колесиком */
        #glassResponseArea {{
            background-color: {ITEM_BG};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: {RADIUS_MD}px;
            color: {TEXT_DIM};
            padding: 10px 12px;
            font-size: 14px;
        }}
        #glassResponseArea:focus {{
            border: 1px solid rgba(255, 255, 255, 0.25);
        }}

        /* Поля промптов на вкладке Промпт — компактные, при фокусе разворачиваются */
        #glassPromptEdit {{
            background-color: {ITEM_BG};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: {RADIUS_MD}px;
            color: {TEXT_DIM};
            padding: 8px 12px;
            font-size: 14px;
        }}
        #glassPromptEdit:focus {{
            border: 1px solid {ACCENT_COLOR};
        }}

        #glassInput:focus {{
            border: 1px solid {ACCENT_COLOR};
            background-color: rgba(0, 0, 0, 0.4);
        }}
        /* Подсветка поля горячей клавиши при фокусе (через свойство hotkeyActive, т.к. Qt не поддерживает :focus-within) */
        #glassKeyEditFrame[hotkeyActive="true"] {{
            border: 2px solid {ACCENT_COLOR};
            background-color: rgba(0, 0, 0, 0.4);
        }}

        /* Переключатель языка RU / EN — при выборе текст остаётся видимым */
        #glassLangSwitch {{
            background-color: {ITEM_BG};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: {RADIUS_SM}px;
            color: {TEXT_DIM};
            font-size: 13px;
            font-weight: 600;
            padding: 10px 24px;
            min-width: 56px;
        }}
        #glassLangSwitch:hover {{
            border-color: rgba(255, 255, 255, 0.3);
            color: {TEXT_BRIGHT};
        }}
        #glassLangSwitch:checked {{
            background-color: {ACCENT_COLOR};
            border-color: {ACCENT_COLOR};
            color: #FFFFFF;
        }}

        /* 4. ВКЛАДКИ (Стиль Modern Segmented) */
        QTabWidget::pane {{ border: none; background: transparent; }}
        
        QTabBar::tab {{
            background: rgba(255, 255, 255, 0.04);
            color: {TEXT_DIM};
            padding: 10px 20px;
            margin-right: 4px;
            border-radius: {RADIUS_SM}px;
            font-weight: 600;
        }}

        QTabBar::tab:selected {{
            background: rgba(255, 255, 255, 0.1);
            color: {ACCENT_COLOR};
            border: 1px solid rgba(255, 184, 108, 0.3);
        }}

        QTabBar::tab:hover:!selected {{
            background: rgba(255, 255, 255, 0.08);
            color: {TEXT_BRIGHT};
        }}

        /* 4.1 Кнопки в шапке: свернуть в трей (−) и закрыть (×) */
        #glassTitleBtn {{
            background-color: {ITEM_BG};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: {RADIUS_SM}px;
            color: {TEXT_BRIGHT};
            font-size: 18px;
            font-weight: 300;
        }}
        #glassTitleBtn:hover {{
            background-color: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.3);
        }}
        #glassTitleBtn:pressed {{
            background-color: rgba(255, 255, 255, 0.05);
        }}

        #glassCloseBtn {{
            background-color: {ITEM_BG};
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: {RADIUS_SM}px;
            color: {TEXT_BRIGHT};
            font-size: 18px;
            font-weight: 300;
        }}
        #glassCloseBtn:hover {{
            background-color: rgba(220, 90, 80, 0.5);
            border-color: rgba(240, 120, 100, 0.6);
            color: #FFFFFF;
        }}
        #glassCloseBtn:pressed {{
            background-color: rgba(200, 70, 60, 0.7);
        }}

        /* 5. ГЛАВНАЯ КНОПКА */
        #glassPrimaryButton {{
            background: {ACCENT_COLOR};
            border-radius: {RADIUS_MD}px;
            color: #1A1A1E; /* Темный текст на светлой кнопке — тренд */
            font-weight: 800;
            font-size: 14px;
            padding: 14px;
            margin-top: 10px;
        }}

        #glassPrimaryButton:hover {{ 
            background: {ACCENT_HOVER}; 
        }}

        #glassPrimaryButton:pressed {{
            background: #E6A75A;
        }}

        /* Кнопки Помощника (Старт/Стоп) — всегда яркие, не сливаются с фоном */
        #glassAssistantButton {{
            background-color: #FF9900;
            color: #000000;
            border: 2px solid #FFCC00;
            border-radius: {RADIUS_MD}px;
            font-weight: 800;
            font-size: 14px;
            padding: 10px 16px;
        }}
        #glassAssistantButton:hover {{
            background-color: #FFB833;
            border-color: #FFDD66;
        }}
        #glassAssistantButton:pressed {{
            background-color: #E68A00;
        }}
        #glassAssistantButton:disabled {{
            background-color: #555555;
            color: #999999;
            border-color: #666666;
        }}

        /* 6. ЧЕКБОКСЫ И ТОГГЛЫ (QCheckBox и #glassToggle — чтобы не перебивалось другими правилами) */
        QCheckBox, QCheckBox#glassToggle {{
            color: {TEXT_BRIGHT};
            spacing: 10px;
            font-size: 13px;
        }}
        /* Размер индикатора один и тот же во всех состояниях — иначе :checked «раздувается» и не помещается */
        QCheckBox::indicator, QCheckBox#glassToggle::indicator,
        QCheckBox::indicator:hover, QCheckBox#glassToggle::indicator:hover,
        QCheckBox::indicator:checked, QCheckBox#glassToggle::indicator:checked,
        QCheckBox::indicator:checked:hover, QCheckBox#glassToggle::indicator:checked:hover,
        QCheckBox::indicator:disabled, QCheckBox#glassToggle::indicator:disabled,
        QCheckBox::indicator:checked:disabled, QCheckBox#glassToggle::indicator:checked:disabled {{
            width: 20px;
            height: 20px;
            min-width: 20px;
            max-width: 20px;
            min-height: 20px;
            max-height: 20px;
            border-radius: 6px;
        }}
        QCheckBox::indicator, QCheckBox#glassToggle::indicator {{
            background-color: rgba(50, 50, 58, 0.9);
            border: 1px solid rgba(255, 255, 255, 0.4);
        }}
        QCheckBox::indicator:hover, QCheckBox#glassToggle::indicator:hover {{
            background-color: rgba(65, 65, 75, 0.95);
            border-color: rgba(255, 255, 255, 0.55);
        }}
        QCheckBox::indicator:checked, QCheckBox#glassToggle::indicator:checked {{
            background-color: rgba(38, 38, 45, 0.95);
            border: 1px solid {CHECK_ORANGE};
        }}
        QCheckBox::indicator:checked:hover, QCheckBox#glassToggle::indicator:checked:hover {{
            background-color: rgba(50, 48, 42, 0.98);
            border-color: #FFB033;
        }}
        QCheckBox::indicator:disabled, QCheckBox#glassToggle::indicator:disabled {{
            background-color: rgba(40, 40, 45, 0.6);
            border-color: rgba(255, 255, 255, 0.15);
        }}
        QCheckBox::indicator:checked:disabled, QCheckBox#glassToggle::indicator:checked:disabled {{
            background-color: rgba(38, 38, 45, 0.8);
            border-color: rgba(255, 153, 0, 0.5);
        }}

        /* 7. СКРОЛЛБАР */
        QScrollBar:vertical {{
            background: transparent;
            width: 5px;
            margin-left: 2px;
        }}
        
        QScrollBar::handle:vertical {{
            background: rgba(255, 255, 255, 0.15);
            border-radius: 2px;
        }}
        
        QScrollBar::handle:vertical:hover {{
            background: {ACCENT_COLOR};
        }}

        /* 8. ПОЛЗУНОК ПРОЗРАЧНОСТИ */
        QSlider::groove:horizontal {{
            background: {ITEM_BG};
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {ACCENT_COLOR};
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {ACCENT_HOVER};
        }}
        QSlider::sub-page:horizontal {{
            background: rgba(255, 184, 108, 0.35);
            border-radius: 3px;
        }}
    """