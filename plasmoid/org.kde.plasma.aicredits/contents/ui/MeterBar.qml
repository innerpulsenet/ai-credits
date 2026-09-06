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

    readonly property bool hasPct: meter.used_pct !== undefined && !meter.expired
    readonly property string level: Severity.of(meterItem.hasPct ? meter.used_pct : -1,
                                                warnPct, criticalPct)

    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents.Label {
            // Eyebrow: small, widely tracked, quiet. Does the labelling work
            // without competing with the figure beside it.
            text: meterItem.meter.label.toUpperCase()
            color: meterItem.owner.inkSoft
            font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.92)
            font.letterSpacing: 0.9
            font.capitalization: Font.AllUppercase
        }

        Item { Layout.fillWidth: true }

        PlasmaComponents.Label {
            text: meterItem.figure()
            font: Kirigami.Theme.smallFont
            color: meterItem.hasPct ? meterItem.owner.usageColor(meterItem.meter.used_pct)
                                    : meterItem.owner.ink
        }
    }

    Rectangle {
        id: track
        visible: meterItem.hasPct
        Layout.fillWidth: true
        Layout.topMargin: 4
        Layout.preferredHeight: 6
        radius: height / 2
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.08)
        border.width: 1
        border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.04)

        Rectangle {
            readonly property real pct: Math.max(0, Math.min(100, meterItem.meter.used_pct || 0))
            width: pct <= 0 ? 0 : Math.max(height, track.width * (pct / 100))
            height: track.height
            radius: track.radius

            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop {
                    position: 0.0
                    color: Qt.tint(meterItem.owner.usageColor(meterItem.meter.used_pct),
                                   Qt.rgba(1, 1, 1, 0.16))
                }
                GradientStop {
                    position: 1.0
                    color: meterItem.owner.usageColor(meterItem.meter.used_pct)
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
        id: resetLabel
        Layout.fillWidth: true
        Layout.topMargin: 3
        visible: text !== ""
        text: {
            if (meterItem.meter.expired)
                return i18n("window already reset");

            const resetTime = meterItem.meter.resets_at
                ? i18n("resets in %1", meterItem.owner.shortDuration(meterItem.meter.resets_at))
                : "";

            const projection = meterItem.meter.projection;
            let paceTime = "";
            if (projection) {
                const hasExhaust = !!projection.exhausts_at;
                const hasPct = projection.projected_pct !== undefined;
                const timeStr = hasExhaust ? meterItem.owner.shortDuration(projection.exhausts_at) : "";

                if (hasPct && hasExhaust) {
                    const isExhaustFirst = meterItem.meter.resets_at && projection.exhausts_at < meterItem.meter.resets_at;
                    if (isExhaustFirst) {
                        paceTime = i18n("on pace for 100% (~%1 to empty)", timeStr);
                    } else {
                        paceTime = i18n("on pace for ~%1% (~%2 to empty)", projection.projected_pct, timeStr);
                    }
                } else if (hasPct) {
                    paceTime = i18n("on pace for ~%1%", projection.projected_pct);
                } else if (hasExhaust) {
                    paceTime = i18n("~%1 to empty", timeStr);
                }
            }

            if (resetTime && paceTime)
                return resetTime + " · " + paceTime;
            if (resetTime)
                return resetTime;
            if (paceTime)
                return paceTime;
            return "";
        }
        color: meterItem.owner.inkSoft
        font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.90)
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
            if (meter.remaining !== undefined && meter.total)
                return Severity.humanCount(meter.remaining) + " of "
                     + Severity.humanCount(meter.total) + " left";
            return Math.round(meter.used_pct) + "% used";
        }
        if (meter.used_pct !== undefined && meter.expired)
            return i18n("was %1%", Math.round(meter.used_pct));
        if (meter.remaining !== undefined)
            return Severity.humanCount(meter.remaining) + " " + (meter.unit || "");
        if (meter.total !== undefined)
            return Severity.humanCount(meter.total) + " " + (meter.unit || "");
        return "";
    }
}
