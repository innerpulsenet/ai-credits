pragma ComponentBehavior: Bound

import QtQuick
import QtCore
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami
import "severity.js" as Severity
import "providerOrder.js" as ProviderOrder

/*
 * The applet owns no network code. A systemd user timer runs the collector,
 * which writes one JSON snapshot; this re-reads that file and draws it. That
 * split is why the panel can never block on a slow vendor API.
 */
PlasmoidItem {
    id: root

    // standardLocations returns QUrls; String() first, then strip the scheme.
    readonly property string homeDir:
        String(StandardPaths.standardLocations(StandardPaths.HomeLocation)[0])
            .replace(/^file:\/\//, "")
    readonly property string statePath: {
        const configured = Plasmoid.configuration.statePath;
        // An absolute path is used as-is; anything else is relative to $HOME.
        return configured.startsWith("/") ? configured
                                          : root.homeDir + "/" + configured;
    }
    // Qt refuses XMLHttpRequest on file:// URLs unless the whole shell is
    // started with QML_XHR_ALLOW_FILE_READ=1, which is not a trade worth making
    // for one JSON file — so the snapshot is read through Plasma's executable
    // data engine instead.
    readonly property string readCommand: 'cat "' + root.statePath + '"'
    readonly property string cliPath: {
        const configured = Plasmoid.configuration.cliPath;
        return configured.startsWith("/") ? configured : root.homeDir + "/" + configured;
    }

    property var snapshotProviders: []
    readonly property var providers: ProviderOrder.sorted(root.snapshotProviders,
                                                          Plasmoid.configuration.providerOrder)
    property var totals: ({})
    property int updatedAt: 0
    property bool loaded: false
    property string loadError: ""
    property bool refreshing: false
    property int nowSeconds: Math.floor(Date.now() / 1000)
    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: root.nowSeconds = Math.floor(Date.now() / 1000)
    }

    readonly property real warnPct: Plasmoid.configuration.warnPct
    readonly property real criticalPct: Plasmoid.configuration.criticalPct

    // The single number the panel shows: the highest usage across everything
    // that reported a usable, current figure.
    readonly property var worst: {
        let top = null;
        for (const provider of root.providers) {
            if (provider.worst_pct === undefined || provider.status !== "ok")
                continue;
            if (top === null || provider.worst_pct > top.worst_pct)
                top = provider;
        }
        return top;
    }

    readonly property int attentionCount: {
        let count = 0;
        for (const provider of root.providers)
            if (Severity.needsAttention(provider.status))
                count += 1;
        return count;
    }

    readonly property int criticalCount: {
        let count = 0;
        for (const provider of root.providers)
            if (provider.status === "ok" && provider.worst_pct !== undefined && provider.worst_pct >= root.criticalPct)
                count += 1;
        return count;
    }

    readonly property int warningCount: {
        let count = 0;
        for (const provider of root.providers)
            if (provider.status === "ok" && provider.worst_pct !== undefined && provider.worst_pct >= root.warnPct && provider.worst_pct < root.criticalPct)
                count += 1;
        return count;
    }

    // ---- tokens -------------------------------------------------------
    // Named for role, not value, and derived from the active Plasma theme so
    // the applet follows the user's colour scheme instead of fighting it.
    readonly property color ink: Kirigami.Theme.textColor
    readonly property color inkSoft: Qt.rgba(Kirigami.Theme.textColor.r,
                                             Kirigami.Theme.textColor.g,
                                             Kirigami.Theme.textColor.b, 0.62)
    readonly property color line: Qt.rgba(Kirigami.Theme.textColor.r,
                                          Kirigami.Theme.textColor.g,
                                          Kirigami.Theme.textColor.b, 0.08)
    readonly property color track: Qt.rgba(Kirigami.Theme.textColor.r,
                                           Kirigami.Theme.textColor.g,
                                           Kirigami.Theme.textColor.b, 0.14)
    readonly property color cardBackground: Qt.rgba(Kirigami.Theme.textColor.r,
                                                    Kirigami.Theme.textColor.g,
                                                    Kirigami.Theme.textColor.b, 0.035)
    readonly property color cardBorder: Qt.rgba(Kirigami.Theme.textColor.r,
                                                Kirigami.Theme.textColor.g,
                                                Kirigami.Theme.textColor.b, 0.08)
    readonly property color cardBorderHover: Qt.rgba(Kirigami.Theme.textColor.r,
                                                     Kirigami.Theme.textColor.g,
                                                     Kirigami.Theme.textColor.b, 0.18)
    readonly property color badgeBackground: Qt.rgba(Kirigami.Theme.textColor.r,
                                                     Kirigami.Theme.textColor.g,
                                                     Kirigami.Theme.textColor.b, 0.08)
    readonly property color badgeBorder: Qt.rgba(Kirigami.Theme.textColor.r,
                                                 Kirigami.Theme.textColor.g,
                                                 Kirigami.Theme.textColor.b, 0.14)

    // Horizontal breathing room. Every part of the popup indents by this, so
    // the title, the provider names and the footer align on one edge.
    readonly property int inset: Math.round(Kirigami.Units.gridUnit * 0.75)

    // Corner radius, defined here rather than taken from Kirigami so it is
    // consistent across the bars, the hover highlight and the sparkline
    // regardless of which Kirigami version is installed.
    readonly property int radius: Math.round(Kirigami.Units.gridUnit * 0.45)
    readonly property int badgeRadius: Math.round(Kirigami.Units.gridUnit * 0.22)
    readonly property color hoverColor: Qt.rgba(Kirigami.Theme.textColor.r,
                                                Kirigami.Theme.textColor.g,
                                                Kirigami.Theme.textColor.b, 0.065)

    // One display size, used only for the figure that matters on each row.
    readonly property int figureSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.38)

    function mixColor(from, to, fraction) {
        const f = Math.max(0, Math.min(1, fraction));
        return Qt.rgba(from.r + (to.r - from.r) * f,
                       from.g + (to.g - from.g) * f,
                       from.b + (to.b - from.b) * f, 1);
    }

    /*
     * Continuous green -> amber -> red ramp across the whole 0-100 range, so a
     * bar's colour alone tells you roughly where a provider stands. The anchors
     * come from the active colour scheme rather than hardcoded hues, so the
     * ramp stays legible on light themes and for anyone using an accessible
     * scheme. Amber is placed at 60% rather than the midpoint: the top of the
     * range is where the reader needs the finer distinction.
     */
    function usageColor(pct) {
        if (pct === undefined || pct === null || pct < 0)
            return Kirigami.Theme.disabledTextColor;
        const t = Math.max(0, Math.min(1, pct / 100));
        return t <= 0.6
            ? root.mixColor(Kirigami.Theme.positiveTextColor,
                            Kirigami.Theme.neutralTextColor, t / 0.6)
            : root.mixColor(Kirigami.Theme.neutralTextColor,
                            Kirigami.Theme.negativeTextColor, (t - 0.6) / 0.4);
    }

    // Kept for meters that carry no percentage at all.
    function levelColor(level) {
        switch (level) {
        case "critical": return Kirigami.Theme.negativeTextColor;
        case "warning":  return Kirigami.Theme.neutralTextColor;
        case "ok":       return Kirigami.Theme.highlightColor;
        default:         return Kirigami.Theme.disabledTextColor;
        }
    }

    function statusLabel(status) {
        switch (status) {
        case "ok": return "";
        case "stale": return i18n("stale");
        case "auth_needed": return i18n("needs setup");
        case "error": return i18n("error");
        case "never_polled": return i18n("not polled");
        default: return status;
        }
    }

    function relativeTime(epochSeconds) {
        if (!epochSeconds)
            return "";
        const seconds = Math.max(0, Math.floor(Date.now() / 1000) - epochSeconds);
        if (seconds < 90) return i18n("just now");
        if (seconds < 5400) return i18n("%1m ago", Math.round(seconds / 60));
        if (seconds < 172800) return i18n("%1h ago", Math.round(seconds / 3600));
        return i18n("%1d ago", Math.round(seconds / 86400));
    }

    // Bare duration ("3h", "4d") for use inside a sentence.
    function shortDuration(epochSeconds) {
        const minutes = Math.max(0, Math.ceil((epochSeconds - root.nowSeconds) / 60));
        if (minutes <= 0) return i18n("moments");
        if (minutes < 60) return i18n("%1m", minutes);
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return i18n("%1h %2m", hours, minutes % 60);
        return i18n("%1d %2h", Math.floor(hours / 24), hours % 24);
    }

    function countdown(epochSeconds) {
        if (!epochSeconds)
            return "";
        const seconds = epochSeconds - Math.floor(Date.now() / 1000);
        if (seconds <= 0) return i18n("reset due");
        if (seconds < 5400) return i18n("resets in %1m", Math.round(seconds / 60));
        if (seconds < 172800) return i18n("resets in %1h", Math.round(seconds / 3600));
        return i18n("resets in %1d", Math.round(seconds / 86400));
    }

    function displayDate(isoDate) {
        if (!isoDate)
            return "";
        const parts = isoDate.split("-");
        if (parts.length !== 3)
            return isoDate;
        const date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
        return Qt.formatDate(date, "MMM d");
    }

    preferredRepresentation: compactRepresentation
    compactRepresentation: CompactRepresentation { plasmoidItem: root }
    fullRepresentation: FullRepresentation { plasmoidItem: root }

    toolTipMainText: i18n("AI Credits")
    toolTipSubText: {
        if (!root.loaded)
            return root.loadError !== "" ? root.loadError : i18n("Waiting for the first snapshot…");
        const parts = [];
        if (root.worst)
            parts.push(i18n("%1 at %2%", root.worst.label, Math.round(root.worst.worst_pct)));
        if (root.attentionCount > 0)
            parts.push(i18np("%1 provider needs attention",
                             "%1 providers need attention", root.attentionCount));
        if (root.totals && root.totals.monthly_usd)
            parts.push(i18n("$%1 per month", root.totals.monthly_usd.toFixed(2)));
        return parts.join("\n");
    }

    Plasmoid.status: (root.attentionCount > 0
                      || (root.worst && root.worst.worst_pct >= root.criticalPct))
                     ? PlasmaCore.Types.ActiveStatus
                     : PlasmaCore.Types.PassiveStatus

    function applySnapshot(text) {
        if (!text) {
            root.loadError = i18n("No snapshot yet — run: aicredits poll");
            return;
        }
        try {
            const data = JSON.parse(text);
            root.snapshotProviders = data.providers || [];
            root.totals = data.totals || ({});
            root.updatedAt = data.updated_at || 0;
            root.loaded = true;
            root.loadError = "";
        } catch (error) {
            root.loadError = i18n("Snapshot is not valid JSON");
        }
    }

    Plasma5Support.DataSource {
        id: reader
        engine: "executable"
        connectedSources: [root.readCommand]
        interval: Math.max(5000, Plasmoid.configuration.readIntervalMs)
        onNewData: function(source, data) {
            if (data["exit code"] !== 0) {
                root.loadError = i18n("Cannot read %1", root.statePath);
                return;
            }
            root.applySnapshot(data["stdout"]);
        }
    }

    function reload() {
        // Force an immediate re-run rather than waiting for the interval.
        reader.disconnectSource(root.readCommand);
        reader.connectSource(root.readCommand);
    }

    Plasma5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        interval: 0
        onNewData: function(source, data) {
            disconnectSource(source);
            root.refreshing = false;
            root.reload();
        }
    }

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'";
    }

    function refreshNow() {
        if (root.refreshing)
            return;
        let command = Plasmoid.configuration.refreshCommand;
        // Preserve genuine custom commands, but upgrade the original default:
        // starting the normal timer service respected provider intervals and
        // therefore did not mean "refresh now".
        if (!command || command === "systemctl --user start aicredits.service")
            command = root.shellQuote(root.cliPath) + " poll --force";
        root.refreshing = true;
        runner.connectSource(command);
    }

    // Re-read the moment the popup opens, so it never shows an old figure just
    // because the read timer has not come around yet.
    onExpandedChanged: if (root.expanded) root.reload()
}
