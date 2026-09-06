pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PlasmaComponents
import "severity.js" as Severity

/*
 * One meter: a tracked label, a figure, and — only when there is a real
 * percentage — a bar. Balance and spend meters that carry no percentage get
 * their figure alone, because an empty bar would imply a "0% used" the data
 * never claimed.
 */
ColumnLayout {
    id: meterItem

    required property var meter
    required property real warnPct
    required property real criticalPct
    required property var owner
    property bool stale: false
    readonly property bool resetDue: !!meter.resets_at && meter.resets_at <= owner.nowSeconds
    readonly property bool atRisk: !stale && !resetDue && !!meter.projection
        && !!meter.resets_at && meter.projection.exhausts_at < meter.resets_at

    readonly property bool hasPct: meter.used_pct !== undefined && !meter.expired && !resetDue
    readonly property string level: Severity.of(meterItem.hasPct ? meter.used_pct : -1,
                                                warnPct, criticalPct)

    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.Label {
            text: meterItem.meter.label.replace(/Weekly/gi, "7d")
            color: meterItem.owner.ink
            font.pixelSize: Kirigami.Theme.smallFont.pixelSize
            font.weight: Font.DemiBold
        }

        Item { Layout.fillWidth: true }

        Sparkline {
            points: meterItem.hasPct ? (meterItem.meter.spark || []) : []
            strokeColor: meterItem.owner.inkSoft
            colorRamp: meterItem.stale ? null
                       : pct => meterItem.owner.usageColor(pct)
            implicitWidth: Kirigami.Units.gridUnit * 2
            implicitHeight: Kirigami.Theme.smallFont.pixelSize
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: Kirigami.Units.smallSpacing
        }

        PlasmaComponents.Label {
            text: meterItem.figure()
            font: Kirigami.Theme.smallFont
            color: meterItem.owner.ink
        }
    }

    Rectangle {
        id: track
        visible: meterItem.hasPct
        Layout.fillWidth: true
        Layout.topMargin: 4
        Layout.preferredHeight: 8
        radius: height / 2
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.08)
        border.width: 1
        border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.04)

        Rectangle {
            id: fill
            readonly property real pct: Math.max(0, Math.min(100, meterItem.meter.used_pct || 0))
            width: pct <= 0 ? 0 : Math.max(height, track.width * (pct / 100))
            height: track.height
            radius: track.radius

            color: meterItem.stale ? meterItem.owner.inkSoft : "transparent"

            /*
             * The fill is painted along the same 0-100 ramp the settings
             * preview shows: its left edge is always the "no usage" green and
             * its right edge the colour for the percentage actually reached, so
             * a filling bar visibly slides green -> amber -> red. Positions are
             * expressed in fill coordinates, which is why the amber anchor is
             * divided by the current percentage.
             */
            gradient: meterItem.stale ? null : usageRamp

            Gradient {
                id: usageRamp
                orientation: Gradient.Horizontal
                GradientStop {
                    position: 0.0
                    color: meterItem.owner.usageColor(0)
                }
                GradientStop {
                    position: fill.pct > meterItem.owner.usageAmberPct
                              ? meterItem.owner.usageAmberPct / fill.pct : 1.0
                    color: fill.pct > meterItem.owner.usageAmberPct
                           ? meterItem.owner.usageColor(meterItem.owner.usageAmberPct)
                           : meterItem.owner.usageColor(fill.pct)
                }
                GradientStop {
                    position: 1.0
                    color: meterItem.owner.usageColor(fill.pct)
                }
            }

            Behavior on width {
                NumberAnimation {
                    duration: Kirigami.Units.longDuration
                    easing.type: Easing.OutCubic
                }
            }
        }
    }

    PlasmaComponents.Label {
        Layout.fillWidth: true
        Layout.topMargin: 4
        visible: text !== ""
        text: meterItem.meter.expired || meterItem.resetDue
              ? i18n("Reset due · refreshing automatically")
              : meterItem.meter.resets_at
                ? i18n("Resets in %1", meterItem.owner.shortDuration(meterItem.meter.resets_at)) : ""
        color: meterItem.owner.ink
        font: Kirigami.Theme.smallFont
        wrapMode: Text.WordWrap
    }

    PlasmaComponents.Label {
        Layout.fillWidth: true
        Layout.topMargin: 2
        visible: text !== ""
        text: {
            if (meterItem.stale || meterItem.meter.expired || meterItem.resetDue)
                return "";
            if (meterItem.meter.used_pct >= 100)
                return i18n("Allowance used up");
            const p = meterItem.meter.projection;
            if (!p)
                return meterItem.meter.kind === "window" ? i18n("Pace estimate unavailable") : "";
            const parts = [];
            if (p.projected_pct !== undefined)
                parts.push(i18n("On pace for ~%1%", p.projected_pct));
            if (p.exhausts_at) {
                if (meterItem.meter.resets_at && p.exhausts_at >= meterItem.meter.resets_at)
                    parts.push(i18n("Resets before empty"));
                else if (p.exhausts_at <= meterItem.owner.nowSeconds)
                    parts.push(i18n("Near empty at this rate"));
                else
                    parts.push(i18n("Empty in ~%1", meterItem.owner.shortDuration(p.exhausts_at)));
            }
            return parts.join(" · ");
        }
        color: meterItem.atRisk ? Kirigami.Theme.neutralTextColor : meterItem.owner.inkSoft
        font: Kirigami.Theme.smallFont
        wrapMode: Text.WordWrap
    }

    function figure() {
        const meter = meterItem.meter;
        if (meter.amount_usd !== undefined) {
            let text = "$" + meter.amount_usd.toFixed(2);
            if (meter.total)
                text += "  " + Severity.humanCount(meter.total) + " " + (meter.unit || "");
            return text;
        }
        if (meterItem.hasPct) {
            if (meter.kind !== "window" && meter.remaining !== undefined && meter.total)
                return Severity.humanCount(meter.remaining) + " of "
                     + Severity.humanCount(meter.total) + " left";
            return Math.round(meter.used_pct) + "% used";
        }
        if (meter.used_pct !== undefined && (meter.expired || meterItem.resetDue))
            return i18n("was %1%", Math.round(meter.used_pct));
        if (meter.remaining !== undefined)
            return Severity.humanCount(meter.remaining) + " " + (meter.unit || "");
        if (meter.total !== undefined)
            return Severity.humanCount(meter.total) + " " + (meter.unit || "");
        return "";
    }
}
