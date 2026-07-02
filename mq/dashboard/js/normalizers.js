// Field accessors that normalize the varied investigation/pattern schemas
// into a single consistent shape for the rest of the app.
//
// Canonical shape is defined by schemas/investigation.schema.json and
// schemas/pattern.schema.json (schema_version "1.0"). Older records
// (produced before that schema existed) use different field names for the
// same concepts, so every accessor here falls back to the legacy field.

import { asList } from "./utils.js";

// The grouping/lookup key must always be the signature *hash*, since that's
// what pattern file names and the investigations index both use.
// - New schema: investigation has "signature_hash" directly.
// - Any schema: the investigations index.json entry (_meta) always carries
//   the hash in its "signature" field, since the index format is unaffected
//   by the investigation schema version.
// - Legacy investigations (no _meta, no signature_hash): "signature" held
//   the hash directly.
export const invSig = i => i.signature_hash || (i._meta && i._meta.signature) || i.signature;

export const invTime = i => i.timestamp || i.timestamp_utc || (i._meta && i._meta.timestamp);
export const invCat = i => i.category || (i._meta && i._meta.category) || "Other";
export const invWf = i => i.workflow_name || i.workflow || (i._meta && i._meta.workflow) || "";

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

// Normalized failed-job entries: { name, conclusion, symptom }.
// Schema: failed_jobs is an array of { name, conclusion?, symptom }.
// Legacy: failed_jobs may be an array of plain strings, or a single
// job_name/failed_job string field.
export function failedJobs(i) {
    const jobs = asList(i.failed_jobs).map(job => {
        if (job && typeof job === "object") {
            return { name: job.name, conclusion: job.conclusion, symptom: job.symptom };
        }
        return { name: job, conclusion: null, symptom: null };
    });
    if (i.job_name) jobs.push({ name: i.job_name, conclusion: null, symptom: null });
    if (i.failed_job) jobs.push({ name: i.failed_job, conclusion: null, symptom: null });

    const seen = new Set();
    return jobs.filter(job => {
        if (!job.name || seen.has(job.name)) return false;
        seen.add(job.name);
        return true;
    });
}

export function jobNames(i) {
    return failedJobs(i).map(job => job.name);
}

// Root cause may be a plain string (schema) or a structured object (legacy).
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

// Schema: reproduction_steps / prevention_strategies / historical_context.
// Legacy: reproduction / prevention / investigation_notes / notes.
export const invReproduction = i => i.reproduction_steps || i.reproduction;
export const invPrevention = i => i.prevention_strategies || i.prevention;
export const invHistory = i => i.historical_context || i.investigation_notes || i.notes;
