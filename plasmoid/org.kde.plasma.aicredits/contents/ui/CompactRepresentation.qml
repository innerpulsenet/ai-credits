pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import "severity.js" as Severity

/* The worst provider as a ring, with its figure set inside. */
Item {
    id: compact

    required property PlasmoidItem plasmoidItem

    readonly property real pct: plasmoidItem.worst ? plasmoidItem.worst.worst_pct : -1
    readonly property string level: Severity.of(compact.pct, plasmoidItem.warnPct,
                                                plasmoidItem.criticalPct)
    readonly property color arcColor: plasmoidItem.usageColor(compact.pct)
    readonly property color trackColor: plasmoidItem.track

    // The arc sweeps to a new reading instead of snapping, which makes a
    // refresh legible out of the corner of your eye. Kirigami durations honour
    // the user's animation-speed setting, so this is inert when they are off.
    property real sweep: 0
    Behavior on sweep {
        NumberAnimation {
            duration: Kirigami.Units.veryLongDuration
            easing.type: Easing.OutCubic
        }
    }
    onPctChanged: compact.sweep = Math.max(0, compact.pct)
    Component.onCompleted: compact.sweep = Math.max(0, compact.pct)

    Layout.minimumWidth: Kirigami.Units.iconSizes.small
    Layout.minimumHeight: Kirigami.Units.iconSizes.small

    onSweepChanged: ring.requestPaint()
    onArcColorChanged: ring.requestPaint()
    onTrackColorChanged: ring.requestPaint()

    Canvas {
        id: ring
        anchors.centerIn: parent
        width: Math.min(compact.width, compact.height)
        height: width

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            const thickness = Math.max(2, width * 0.13);
            const radius = (width - thickness) / 2;
            if (radius <= 0)
                return;
            const cx = width / 2;
            const cy = height / 2;
            const start = -Math.PI / 2;

            ctx.lineWidth = thickness;
            ctx.strokeStyle = compact.trackColor;
            ctx.beginPath();
            ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
            ctx.stroke();

            if (compact.sweep > 0 && compact.pct >= 0) {
                ctx.strokeStyle = compact.arcColor;
                ctx.lineCap = "round";
                ctx.beginPath();
                ctx.arc(cx, cy, radius, start,
                        start + 2 * Math.PI * Math.min(1, compact.sweep / 100));
                ctx.stroke();
            }
        }
        onWidthChanged: requestPaint()
        Component.onCompleted: requestPaint()
    }

    Text {
        anchors.centerIn: parent
        visible: compact.pct >= 0 && compact.height >= Kirigami.Units.iconSizes.small
        text: Math.round(compact.pct)
        color: compact.plasmoidItem.ink
        font.pixelSize: Math.max(7, Math.round(compact.height * 0.40))
        font.weight: Font.DemiBold
        font.letterSpacing: -0.4
    }

    // Nothing readable yet: say so rather than drawing an empty ring, which
    // would be indistinguishable from 0% used.
    Kirigami.Icon {
        anchors.centerIn: parent
        width: Math.round(parent.width * 0.5)
        height: width
        visible: compact.pct < 0
        source: compact.plasmoidItem.loaded ? "dialog-question" : "view-refresh"
    }

    Rectangle {
        visible: compact.plasmoidItem.attentionCount > 0
        width: Math.max(4, Math.round(compact.width * 0.20))
        height: width
        radius: width / 2
        color: Kirigami.Theme.neutralTextColor
        border.width: 1
        border.color: Kirigami.Theme.backgroundColor
        anchors { right: parent.right; top: parent.top; rightMargin: 1; topMargin: 1 }
    }

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        onClicked: mouse => {
            if (mouse.button === Qt.MiddleButton)
                compact.plasmoidItem.refreshNow();
            else
                compact.plasmoidItem.expanded = !compact.plasmoidItem.expanded;
        }
    }
}
