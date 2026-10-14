//! Python objects cross the boundary once; no intermediate JSON transport.
//! Hashing remains in Python to preserve the canonical wire representation.
use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFloat, PyInt, PyList, PyString};
use std::collections::HashSet;

create_exception!(singularity_native, InvalidInput, PyValueError);
// Python's reference accepts custom equality for some enum fields. Delegate
// those unusual in-process objects rather than changing their semantics.
create_exception!(singularity_native, UnsupportedInput, PyValueError);

const POLICY: &str = "support/v3";
const DETAILS: [&str; 3] = ["gpu", "fonts", "canvas"];
const SIGNALS: [&str; 5] = ["platform", "cores", "memory", "language", "timezone"];

fn invalid(code: &str) -> PyErr {
    InvalidInput::new_err(code.to_owned())
}

fn record<'py>(value: &Bound<'py, PyAny>, keys: &[&str]) -> PyResult<Bound<'py, PyDict>> {
    if !value.is_exact_instance_of::<PyDict>() {
        return Err(invalid("INVALID_INPUT"));
    }
    let dict = value.cast::<PyDict>()?;
    if dict.len() != keys.len() {
        return Err(invalid("INVALID_INPUT"));
    }
    for key in keys {
        if !dict.contains(key)? {
            return Err(invalid("INVALID_INPUT"));
        }
    }
    Ok(dict.clone())
}

fn get<'py>(dict: &Bound<'py, PyDict>, key: &str) -> PyResult<Bound<'py, PyAny>> {
    dict.get_item(key)?.ok_or_else(|| invalid("INVALID_INPUT"))
}

fn string(value: &Bound<'_, PyAny>) -> PyResult<String> {
    if !value.is_exact_instance_of::<PyString>() {
        return Err(invalid("INVALID_INPUT"));
    }
    value.extract().map_err(|_| invalid("INVALID_INPUT"))
}

fn identifier(value: &Bound<'_, PyAny>, scope: bool) -> PyResult<String> {
    let text = string(value)?;
    if !(1..=128).contains(&text.len())
        || !text
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._:-".contains(&b) || (scope && b == b'/'))
    {
        return Err(invalid("INVALID_INPUT"));
    }
    Ok(text)
}

fn enum_value(value: &Bound<'_, PyAny>, allowed: &[&str]) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    if !value.is_exact_instance_of::<PyString>() {
        return Err(UnsupportedInput::new_err("Python enum equality required"));
    }
    let text = string(value)?;
    if !allowed.contains(&text.as_str()) {
        return Err(invalid("INVALID_INPUT"));
    }
    Ok(Some(text))
}

fn revision(value: &Bound<'_, PyAny>, expected: &str) -> PyResult<()> {
    if !value.is_exact_instance_of::<PyString>() {
        return Err(UnsupportedInput::new_err("Python schema equality required"));
    }
    // Python strings containing lone surrogates are still mismatched revisions,
    // even though they cannot be extracted as a UTF-8 Rust string.
    let text: String = value
        .extract()
        .map_err(|_| invalid("INCOMPATIBLE_SCHEMA"))?;
    if text != expected {
        return Err(invalid("INCOMPATIBLE_SCHEMA"));
    }
    Ok(())
}

fn bucket(value: &Bound<'_, PyAny>, allowed: &[f64]) -> PyResult<Option<f64>> {
    if value.is_none() {
        return Ok(None);
    }
    if !value.is_exact_instance_of::<PyInt>() && !value.is_exact_instance_of::<PyFloat>() {
        return Err(invalid("INVALID_INPUT"));
    }
    let number: f64 = value.extract().map_err(|_| invalid("INVALID_INPUT"))?;
    if !allowed.contains(&number) {
        return Err(invalid("INVALID_INPUT"));
    }
    Ok(Some(number))
}

fn locale(value: &Bound<'_, PyAny>, language: bool) -> PyResult<()> {
    if value.is_none() {
        return Ok(());
    }
    let text = string(value)?;
    let valid = if language {
        (2..=8).contains(&text.len()) && text.bytes().all(|b| b.is_ascii_lowercase())
    } else {
        (1..=80).contains(&text.len())
            && text
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"_+/-".contains(&b))
    };
    if !valid {
        return Err(invalid("INVALID_INPUT"));
    }
    Ok(())
}

struct Snapshot {
    scope: String,
    engine: Option<String>,
    platform: Option<String>,
    cores: Option<f64>,
    detail: [Option<String>; 3],
}

fn parse(value: &Bound<'_, PyAny>) -> PyResult<Snapshot> {
    let s = record(
        value,
        &["schema", "scope", "signals", "probe", "engine", "detail"],
    )?;
    revision(&get(&s, "schema")?, "singularity/v3")?;
    revision(&get(&s, "probe")?, "web/v2")?;
    let engine = enum_value(&get(&s, "engine")?, &["blink", "gecko", "webkit"])?;
    let scope = identifier(&get(&s, "scope")?, true)?;
    let signals = record(&get(&s, "signals")?, &SIGNALS)?;
    let platform = enum_value(
        &get(&signals, "platform")?,
        &["windows", "macos", "ios", "android", "linux", "chromeos"],
    )?;
    let cores = bucket(&get(&signals, "cores")?, &[1., 2., 4., 8., 16., 32., 64.])?;
    bucket(
        &get(&signals, "memory")?,
        &[0.25, 0.5, 1., 2., 4., 8., 16., 32., 64.],
    )?;
    locale(&get(&signals, "language")?, true)?;
    locale(&get(&signals, "timezone")?, false)?;
    let details = record(&get(&s, "detail")?, &DETAILS)?;
    let mut detail = [None, None, None];
    for (i, key) in DETAILS.iter().enumerate() {
        let raw = get(&details, key)?;
        if !raw.is_none() {
            let text = string(&raw)?;
            if text.len() != 64
                || !text
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            {
                return Err(invalid("INVALID_INPUT"));
            }
            detail[i] = Some(text);
        }
    }
    Ok(Snapshot {
        scope,
        engine,
        platform,
        cores,
        detail,
    })
}

#[pyfunction]
fn validate<'py>(py: Python<'py>, value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    parse(value)?;
    let s = value.cast::<PyDict>()?;
    let output = PyDict::new(py);
    for key in ["schema", "scope"] {
        output.set_item(key, get(s, key)?)?;
    }
    output.set_item("signals", get(s, "signals")?.cast::<PyDict>()?.copy()?)?;
    for key in ["probe", "engine"] {
        output.set_item(key, get(s, key)?)?;
    }
    output.set_item("detail", get(s, "detail")?.cast::<PyDict>()?.copy()?)?;
    Ok(output)
}

struct Comparison {
    comparable: Vec<&'static str>,
    supporting: Vec<&'static str>,
    contradictions: Vec<&'static str>,
    differences: Vec<&'static str>,
    qualifies: bool,
}

fn compare(a: &Snapshot, b: &Snapshot) -> Comparison {
    let mut c = Comparison {
        comparable: Vec::with_capacity(3),
        supporting: Vec::with_capacity(3),
        contradictions: Vec::with_capacity(5),
        differences: Vec::with_capacity(3),
        qualifies: false,
    };
    if a.platform.is_some() && b.platform.is_some() && a.platform != b.platform {
        c.contradictions.push("platform");
    }
    if a.cores.is_some() && b.cores.is_some() && a.cores != b.cores {
        c.contradictions.push("cores");
    }
    let cross_engine = a.engine.is_some() && b.engine.is_some() && a.engine != b.engine;
    for (i, key) in DETAILS.iter().enumerate() {
        if let (Some(left), Some(right)) = (&a.detail[i], &b.detail[i]) {
            c.comparable.push(key);
            if left == right {
                c.supporting.push(key);
            } else {
                c.differences.push(key);
                if *key != "canvas" || !cross_engine {
                    c.contradictions.push(key);
                }
            }
        }
    }
    c.qualifies = a.platform.is_some()
        && b.platform.is_some()
        && a.cores.is_some()
        && b.cores.is_some()
        && c.contradictions.is_empty()
        && c.supporting.contains(&"fonts")
        && (c.supporting.contains(&"gpu") || c.supporting.contains(&"canvas"));
    c
}

fn comparison_dict<'py>(py: Python<'py>, id: &str, c: &Comparison) -> PyResult<Bound<'py, PyDict>> {
    let output = PyDict::new(py);
    output.set_item("id", id)?;
    output.set_item("policy", POLICY)?;
    output.set_item("similarity", c.supporting.len() as f64 / 3.)?;
    output.set_item("coverage", c.comparable.len() as f64 / 3.)?;
    output.set_item("comparableDetails", &c.comparable)?;
    output.set_item("supportingDetails", &c.supporting)?;
    output.set_item("contradictions", &c.contradictions)?;
    output.set_item("differences", &c.differences)?;
    output.set_item("qualifies", c.qualifies)?;
    Ok(output)
}

#[pyfunction]
fn match_resilient<'py>(
    py: Python<'py>,
    snapshot: &Bound<'py, PyAny>,
    candidates: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    if !candidates.is_exact_instance_of::<PyList>() {
        return Err(invalid("INVALID_INPUT"));
    }
    let candidates = candidates.cast::<PyList>()?;
    if candidates.len() > 256 {
        return Err(invalid("LIMIT_EXCEEDED"));
    }
    let observation = parse(snapshot)?;
    let mut ids = HashSet::with_capacity(candidates.len());
    let ranking = PyList::empty(py);
    let mut eligible = Vec::new();
    let mut incomplete = false;
    for candidate in candidates.iter() {
        let entry = record(&candidate, &["id", "snapshot"])?;
        let id = identifier(&get(&entry, "id")?, false)?;
        if !ids.insert(id.clone()) {
            return Err(invalid("DUPLICATE_ID"));
        }
        let other = parse(&get(&entry, "snapshot")?)?;
        if other.scope != observation.scope {
            return Err(invalid("SCOPE_MISMATCH"));
        }
        let comparison = compare(&observation, &other);
        if comparison.qualifies {
            eligible.push(id.clone());
        } else if comparison.contradictions.is_empty() {
            incomplete = true;
        }
        ranking.append(comparison_dict(py, &id, &comparison)?)?;
    }
    let (status, reason, winner) = if !compare(&observation, &observation).qualifies {
        ("abstain", "insufficient-detail", None)
    } else if candidates.is_empty() {
        ("unmatched", "no-candidates", None)
    } else if eligible.len() > 1 {
        ("abstain", "ambiguous-candidates", None)
    } else if incomplete {
        ("abstain", "insufficient-candidate-evidence", None)
    } else if let Some(id) = eligible.first() {
        ("matched", "supported-candidate", Some(id.as_str()))
    } else {
        ("unmatched", "no-candidate-qualified", None)
    };
    let output = PyDict::new(py);
    output.set_item("policy", POLICY)?;
    output.set_item("status", status)?;
    output.set_item("candidateId", winner)?;
    output.set_item("reason", reason)?;
    output.set_item("candidates", ranking)?;
    output.set_item("omissions", PyList::empty(py))?;
    Ok(output)
}

#[pymodule]
fn singularity_native(py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("CONTRACT_VERSION", 1)?;
    module.add("InvalidInput", py.get_type::<InvalidInput>())?;
    module.add("UnsupportedInput", py.get_type::<UnsupportedInput>())?;
    module.add_function(wrap_pyfunction!(validate, module)?)?;
    module.add_function(wrap_pyfunction!(match_resilient, module)?)?;
    Ok(())
}
