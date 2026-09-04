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
        Layout.topMargin: 2
        Layout.preferredHeight: 4
        radius: height / 2
        // Alpha in the colour, not opacity on the item: an item's opacity
        // multiplies into its children, which would fade the fill too.
        color: meterItem.owner.track

        Rectangle {
            width: Math.max(height, track.width * Math.min(1, (meterItem.meter.used_pct || 0) / 100))
            height: track.height
            radius: track.radius
            color: meterItem.owner.usageColor(meterItem.meter.used_pct)

            // Kirigami durations already follow the user's animation-speed
            // setting, so this is silent when animations are turned off.
            Behavior on width {
                NumberAnimation {
                    duration: Kirigami.Units.longDuration
                    easing.type: Easing.OutCubic
                }
            }
            Behavior on color {
                ColorAnimation { duration: Kirigami.Units.longDuration }
            }
        }
    }

    PlasmaComponents.Label {
        visible: text !== ""
        text: {
            if (meterItem.meter.expired)
                return i18n("window already reset");
            const projection = meterItem.meter.projection;
            if (projection && projection.exhausts_at)
                return i18n("on pace to run out in %1",
                            meterItem.owner.shortDuration(projection.exhausts_at));
            if (meterItem.meter.resets_at)
                return i18n("resets in %1", meterItem.owner.shortDuration(meterItem.meter.resets_at));
            return "";
        }
        color: meterItem.owner.inkSoft
        font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.92)
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
