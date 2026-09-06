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
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
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
        const padding = 2;
        const availableHeight = height - padding * 2;

        // 1. Build line path
        ctx.beginPath();
        let lastX = 0;
        let lastY = height / 2;
        for (let i = 0; i < points.length; ++i) {
            const x = i * step;
            const y = height - padding - ((points[i] - low) / span) * availableHeight;
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
            lastX = x;
            lastY = y;
        }

        // 2. Fill gradient area under curve
        ctx.save();
        ctx.lineTo(width, height);
        ctx.lineTo(0, height);
        ctx.closePath();
        const grad = ctx.createLinearGradient(0, 0, 0, height);
        grad.addColorStop(0, Qt.rgba(strokeColor.r, strokeColor.g, strokeColor.b, 0.28));
        grad.addColorStop(1, Qt.rgba(strokeColor.r, strokeColor.g, strokeColor.b, 0.0));
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.restore();

        // 3. Stroke the curve
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1.75;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        for (let i = 0; i < points.length; ++i) {
            const x = i * step;
            const y = height - padding - ((points[i] - low) / span) * availableHeight;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();

        // 4. Draw endpoint dot
        ctx.fillStyle = strokeColor;
        ctx.beginPath();
        ctx.arc(lastX - 1, lastY, 1.8, 0, 2 * Math.PI);
        ctx.fill();
    }
}
