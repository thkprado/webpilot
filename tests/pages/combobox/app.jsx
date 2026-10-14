// react-select comboboxes for testing WebPilot by hand (see README.md). The first one copies the
// "How can we help?" field of https://www.npmjs.com/support (react-select 5, classNamePrefix
// "react-select", a hidden input named after the field).
import { useState, version } from "react";
import { render } from "#root"; // root19.js or root17.js, see build.mjs
import Select from "react-select";

const opts = (labels) => labels.map((label, i) => ({ value: `v${i}`, label }));

const INQUIRE = opts([
  "Choose one of the following",
  "There is a problem with the npm registry",
  "My package publish is blocked or delayed",
  "I have an account or billing issue",
  "I'm reporting spam, abuse or a security issue",
  "I want to claim a username, organization name, or package name",
]);
const COUNTRIES = opts([
  "Argentina", "Australia", "Austria", "Belgium", "Bolivia", "Brazil", "Canada", "Chile", "China",
  "Colombia", "Costa Rica", "Croatia", "Cuba", "Czechia", "Denmark", "Ecuador", "Egypt", "Finland",
  "France", "Germany", "Greece", "Guatemala", "Honduras", "Hungary", "Iceland", "India", "Indonesia",
  "Ireland", "Israel", "Italy", "Japan", "Kenya", "Mexico", "Morocco", "Netherlands", "New Zealand",
  "Nigeria", "Norway", "Panama", "Paraguay", "Peru", "Poland", "Portugal", "Romania", "Spain",
  "Sweden", "Switzerland", "Turkey", "Ukraine", "United Kingdom", "United States", "Uruguay", "Venezuela",
]);
const PLANS = opts(["Free", "Pro", "Teams", "Enterprise"]);
const TOPICS = opts(["Billing", "Bug report", "Feature request", "Security", "Other"]);

// What the page did, for diagnosing: read it with `webpilot eval "__events"`.
const events = (window.__events = []);
const log = (field, what, extra) => events.push({ t: Math.round(performance.now()), field, what, ...extra });

const FIELDS = [
  { name: "inquire", label: "How can we help?", options: INQUIRE, props: { defaultValue: INQUIRE[0] } },
  { name: "country", label: "Country (long list)", options: COUNTRIES, props: {} },
  { name: "plan", label: "Plan (not searchable)", options: PLANS, props: { isSearchable: false } },
  {
    name: "topic",
    label: "Topic (menu in a portal, closes on scroll)",
    options: TOPICS,
    props: { menuPortalTarget: document.body, closeMenuOnScroll: true },
  },
];

function Field({ name, label, options, props, onValue }) {
  const id = `field-${name}`;
  return (
    <div className="field">
      <label htmlFor={id} id={`${id}-label`}>{label}</label>
      <Select
        inputId={id}
        instanceId={name}
        name={name}
        classNamePrefix="react-select"
        aria-labelledby={`${id}-label`}
        options={options}
        onChange={(o, meta) => { log(name, "change", { value: o?.label, action: meta.action }); onValue(name, o?.label ?? null); }}
        onInputChange={(v, meta) => { log(name, "input", { value: v, action: meta.action }); }}
        onMenuOpen={() => { log(name, "menu-open"); }}
        onMenuClose={() => { log(name, "menu-close"); }}
        {...props}
      />
    </div>
  );
}

function App() {
  const [values, setValues] = useState(() =>
    Object.fromEntries(FIELDS.map((f) => [f.name, f.props.defaultValue?.label ?? null])),
  );
  const onValue = (name, v) => setValues((s) => ({ ...s, [name]: v }));
  return (
    <form onSubmit={(e) => e.preventDefault()}>
      {FIELDS.map((f) => <Field key={f.name} {...f} onValue={onValue} />)}
      <div className="field">
        <label htmlFor="native">Native select (for comparison)</label>
        <select id="native" defaultValue="">
          <option value="" disabled>Select...</option>
          {PLANS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      <h2>State</h2>
      <pre id="state">{JSON.stringify(values, null, 2)}</pre>
    </form>
  );
}

render(<App />, document.getElementById("root"));

document.getElementById("react-version").textContent = `React ${version}`;
