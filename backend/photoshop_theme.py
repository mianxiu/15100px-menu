"""Read-only interface preference query; no document or preference mutation."""
THEMES = {
    'kPanelBrightnessOriginal': 'light',
    'kPanelBrightnessLightGray': 'light-gray',
    'kPanelBrightnessMediumGray': 'dark-gray',
    'kPanelBrightnessDarkGray': 'dark',
}
THEME_SCRIPT = '''(function () {
    var s = stringIDToTypeID, r = new ActionReference();
    r.putProperty(s('property'), s('interfacePrefs'));
    r.putEnumerated(s('application'), s('ordinal'), s('targetEnum'));
    return typeIDToStringID(executeActionGet(r).getObjectValue(s('interfacePrefs'))
        .getEnumerationValue(s('kuiBrightnessLevel')));
}())'''


def read_theme(app, previous='dark'):
    try:
        return THEMES.get(str(app.DoJavaScript(THEME_SCRIPT)), previous)
    except Exception:
        # Modal dialogs / unsupported versions must not imply disconnection.
        return previous


def read_font_size(app, previous='small'):
    try:
        value = str(app.DoJavaScript('String(app.preferences.textFontSize)'))
        return {'FontSize.SMALL': 'small', 'FontSize.MEDIUM': 'medium',
                'FontSize.LARGE': 'large'}.get(value, previous)
    except Exception:
        return previous
