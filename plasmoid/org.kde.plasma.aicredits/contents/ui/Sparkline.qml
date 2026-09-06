import QtQuick
import org.kde.kirigami as Kirigami

/* Recent history of one meter — enough to see a direction, not a chart. */
Canvas {
    id: spark

    property var points: []
    property color strokeColor: Kirigami.Theme.highlightColor

    /*
     * Optional pct -> colour ramp. When set, the curve is stroked along it so
     * each sample is drawn in the colour of the usage it represents; the line
     * itself then reads green -> red as the meter fills. Worth the extra
     * channel here because the plot is auto-scaled to its own low/high, so
     * height alone never says whether the series sits at 10% or 90%.
     */
    property var colorRamp: null
    readonly property color latestColor:
        (colorRamp && points && points.length) ? colorRamp(points[points.length - 1])
                                               : strokeColor

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
    onColorRampChanged: requestPaint()

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
        const wash = spark.latestColor;
        const grad = ctx.createLinearGradient(0, 0, 0, height);
        grad.addColorStop(0, Qt.rgba(wash.r, wash.g, wash.b, 0.28));
        grad.addColorStop(1, Qt.rgba(wash.r, wash.g, wash.b, 0.0));
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.restore();

        // 3. Stroke the curve
        ctx.strokeStyle = spark.rampStyle(ctx);
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
        ctx.fillStyle = spark.latestColor;
        ctx.beginPath();
        ctx.arc(lastX - 1, lastY, 1.8, 0, 2 * Math.PI);
        ctx.fill();
    }

    // One stop per sample, so the ramp bends exactly where the data does.
    function rampStyle(ctx) {
        if (!spark.colorRamp)
            return spark.strokeColor;
        const grad = ctx.createLinearGradient(0, 0, spark.width, 0);
        for (let i = 0; i < spark.points.length; ++i)
            grad.addColorStop(i / (spark.points.length - 1), spark.colorRamp(spark.points[i]));
        return grad;
    }
}
