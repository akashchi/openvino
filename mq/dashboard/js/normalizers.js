// Field accessors that normalize the varied investigation/pattern schemas
// into a single consistent shape for the rest of the app.

import { asList } from "./utils.js";

export const invSig = i => i.signature || (i._meta && i._meta.signature);
export const invTime = i => i.timestamp || i.timestamp_utc || (i._meta && i._meta.timestamp);
export const invCat = i => i.category || (i._meta && i._meta.category) || "Other";
export const invWf = i => i.workflow || (i._meta && i._meta.workflow) || "";

export function invTitle(i, patterns) {
    const pattern = patterns[invSig(i)];
    return i.title || (pattern && pattern.title) || i.summary || ("Run " + (i.run_id || ""));
}

export function invPR(i) {
    if (i.pr && typeof i.pr === "object") {
        return { number: i.pr.number, url: i.pr.url, author: i.pr.author, title: i.pr.title };
    }
    return { number: i.pr_number, url: i.pr_url, author: i.pr_author || i.author, title: i.pr_title };
}

export function invRunUrl(i) {
    if (i.run_url) return i.run_url;
    return i.run_id ? `https://github.com/openvinotoolkit/openvino/actions/runs/${i.run_id}` : null;
}

export function jobNames(i) {
    const names = [];
    asList(i.failed_jobs).forEach(job => names.push(typeof job === "object" ? job.name : job));
    if (i.job_name) names.push(i.job_name);
    if (i.failed_job) names.push(i.failed_job);
    return [...new Set(names.filter(Boolean))];
}

// Root cause may be a plain string or a structured object.
export function rootCause(i) {
    const rc = i.root_cause;
    if (rc && typeof rc === "object") {
        return { text: rc.explanation, cls: rc.classification, conf: rc.confidence, evidence: rc.evidence };
    }
    return { text: rc, cls: null, conf: i.confidence, evidence: null };
}

// Collect all distinct error/evidence strings from the various fields.
export function errorList(i) {
    const { evidence } = rootCause(i);
    let errors = [];
    if (i.key_errors) errors = errors.concat(asList(i.key_errors));
    if (i.primary_error) errors.push(i.primary_error);
    if (evidence) errors = errors.concat(asList(evidence));
    return [...new Set(errors.filter(Boolean))];
}
