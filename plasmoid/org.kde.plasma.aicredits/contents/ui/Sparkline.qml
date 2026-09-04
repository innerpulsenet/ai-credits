import QtQuick
import org.kde.kirigami as Kirigami

/* Recent history of one meter — enough to see a direction, not a chart. */
Canvas {
    id: spark

    property var points: []
    property color strokeColor: Kirigami.Theme.highlightColor

    // A flat series says nothing; drawing it puts a meaningless dash under
    // every figure, so it only appears once there is movement to show.
    readonly property bool hasVariation: {
        if (!points || points.length < 2)
            return false;
        for (let i = 1; i < points.length; ++i)
            if (points[i] !== points[0])
                return true;
        return false;
    }

    visible: hasVariation
    opacity: 0.9
    onPointsChanged: requestPaint()
    onStrokeColorChanged: requestPaint()

    onPaint: {
        const ctx = getContext("2d");
        ctx.reset();
        if (!points || points.length < 2)
            return;

        let low = points[0], high = points[0];
        for (const value of points) {
            low = Math.min(low, value);
            high = Math.max(high, value);
        }
        const span = Math.max(1, high - low);
        const step = width / (points.length - 1);

        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1.5;
        ctx.lineJoin = "round";
        ctx.beginPath();
        for (let i = 0; i < points.length; ++i) {
            const x = i * step;
            const y = height - ((points[i] - low) / span) * (height - 2) - 1;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
    }
}
