.pragma library

/*
 * Pure threshold logic, shared by the ring, the bars and the tooltip so they
 * can never disagree about which provider is in trouble.
 */

function of(pct, warnPct, criticalPct) {
    if (pct === undefined || pct === null || pct < 0)
        return "unknown";
    if (pct >= criticalPct)
        return "critical";
    if (pct >= warnPct)
        return "warning";
    return "ok";
}

function needsAttention(status) {
    return status !== "ok" && status !== "manual";
}

function humanCount(value) {
    const units = [[1e9, "B"], [1e6, "M"], [1e3, "k"]];
    for (const [limit, suffix] of units)
        if (Math.abs(value) >= limit)
            return (value / limit).toFixed(1) + suffix;
    return String(Math.round(value * 100) / 100);
}
