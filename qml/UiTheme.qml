pragma Singleton
import QtQuick

QtObject {
    id: theme
    readonly property bool darkMode: typeof backend !== "undefined" && backend !== null && backend.settingsModule !== null && backend.settingsModule.appearanceMode === "dark"
    readonly property color canvas: darkMode ? "#141c27" : "#eef2f6"
    readonly property color surface: darkMode ? "#1e2938" : "#ffffff"
    readonly property color ink: darkMode ? "#e6edf7" : "#203047"
    readonly property color muted: darkMode ? "#b1bfd1" : "#596b80"
    readonly property color subtle: darkMode ? "#93a4bb" : "#98a2b3"
    readonly property color line: darkMode ? "#3a4a60" : "#dce3eb"
    readonly property color accent: darkMode ? "#91b9ff" : "#285db4"
    readonly property color accentFill: darkMode ? "#3568b9" : "#285db4"
    readonly property color accentText: "#ffffff"
    readonly property color selection: darkMode ? "#2a4163" : "#e5eefc"
    readonly property color stripe: darkMode ? "#243142" : "#f7f9fc"
    readonly property color input: darkMode ? "#192332" : "#f9fafb"
    readonly property color hover: darkMode ? "#30435e" : "#edf3fc"
    readonly property color pressed: darkMode ? "#3a506f" : "#e5ebf3"
    readonly property color accentHover: darkMode ? "#4278cb" : "#214f9b"
    readonly property color accentPressed: darkMode ? "#2b579c" : "#1c458b"
    readonly property color focus: darkMode ? "#a6c7ff" : "#809aff"
    readonly property color disabledText: darkMode ? "#8c9bb0" : "#8795a6"
    readonly property color disabledSurface: darkMode ? "#283344" : "#f0f3f6"
    readonly property color warning: darkMode ? "#f1bd73" : "#9b5d13"
    readonly property color warningSurface: darkMode ? "#463825" : "#fff4e5"
    readonly property color success: darkMode ? "#7bd8b0" : "#027a48"
    readonly property color successSurface: darkMode ? "#203e35" : "#ecfdf3"
    readonly property color successLine: darkMode ? "#395e50" : "#d3f1e0"
    readonly property color danger: darkMode ? "#ffaaa2" : "#b42318"
    readonly property color dangerSurface: darkMode ? "#492e32" : "#fff1f0"
    readonly property color chartSuccess: darkMode ? "#7bd8b0" : "#14765a"
    readonly property color chartGrid: darkMode ? "#3a4a60" : "#e7edf3"
    readonly property color navigation: darkMode ? "#101823" : "#203047"
    readonly property color navigationText: "#f2f6fc"
    readonly property color navigationMuted: "#b8c9df"
    readonly property color navigationHover: darkMode ? "#293a52" : "#304660"
    readonly property color navigationFocus: "#bcd3fa"
    readonly property color toastSurface: darkMode ? "#dce6f5" : "#203047"
    readonly property color toastText: darkMode ? "#182333" : "#ffffff"
    readonly property color modalOverlay: "#660f172a"
    // Standard Fusion controls, menus and independent windows share this palette.
    readonly property Palette controlPalette: Palette {
        window: theme.surface
        windowText: theme.ink
        base: theme.surface
        alternateBase: theme.stripe
        text: theme.ink
        button: theme.surface
        buttonText: theme.ink
        highlight: theme.accentFill
        highlightedText: theme.accentText
        toolTipBase: theme.surface
        toolTipText: theme.ink
        placeholderText: theme.muted
        light: theme.line
        midlight: theme.stripe
        mid: theme.line
        dark: theme.line
        shadow: theme.canvas
        link: theme.accent
        linkVisited: theme.accent
        disabled {
            text: theme.disabledText
            windowText: theme.disabledText
            buttonText: theme.disabledText
            button: theme.disabledSurface
            base: theme.disabledSurface
        }
    }
    function chartColor(color) {
        var value = String(color).toLowerCase()
        if (value === "#285db4") return accent
        if (value === "#14765a") return chartSuccess
        if (value === "#9b5d13") return warning
        return color
    }
    readonly property int rowHeight: 32
    readonly property int headerHeight: 38
}
