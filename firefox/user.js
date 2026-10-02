// ~/.config/xmonad/firefox/user.js
// linked into the firefox profile; applied every time firefox starts

// load chrome/userChrome.css + chrome/userContent.css
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
user_pref("svg.context-properties.content.enabled", true);

// dark everything: built-in dark theme, dark websites, dark internal pages
user_pref("extensions.activeThemeID", "firefox-compact-dark@mozilla.org");
user_pref("layout.css.prefers-color-scheme.content-override", 0);
user_pref("browser.theme.content-theme", 0);
user_pref("browser.theme.toolbar-theme", 0);
user_pref("ui.systemUsesDarkTheme", 1);

// compact, no title bar buttons (xmonad manages windows), horizontal tabs
user_pref("browser.compactmode.show", true);
user_pref("browser.uidensity", 1);
user_pref("browser.tabs.inTitlebar", 0);
user_pref("sidebar.verticalTabs", false);
user_pref("browser.toolbars.bookmarks.visibility", "never");

// quiet new tab: no sponsored stuff, stories, weather or shortcuts
user_pref("browser.newtabpage.activity-stream.showSponsored", false);
user_pref("browser.newtabpage.activity-stream.showSponsoredTopSites", false);
user_pref("browser.newtabpage.activity-stream.feeds.section.topstories", false);
user_pref("browser.newtabpage.activity-stream.feeds.topsites", false);
user_pref("browser.newtabpage.activity-stream.showWeather", false);
user_pref("browser.newtabpage.activity-stream.feeds.weatherfeed", false);
user_pref("browser.newtabpage.activity-stream.feeds.section.highlights", false);
user_pref("browser.newtabpage.activity-stream.feeds.snippets", false);
user_pref("browser.newtabpage.activity-stream.logowordmark.alwaysVisible", false);
user_pref("browser.newtabpage.activity-stream.newtabWallpapers.enabled", false);

// simple tab tooltips instead of the big hover cards
user_pref("browser.tabs.hoverPreview.enabled", false);
user_pref("browser.tabs.hoverPreview.showThumbnails", false);

// frosted look: let the window and the new tab page be see-through (picom blurs behind)
user_pref("browser.tabs.allow_transparent_browser", true);
user_pref("mozilla.widget.use-argb-visuals", true);
user_pref("layout.css.backdrop-filter.enabled", true);
