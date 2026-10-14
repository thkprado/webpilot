// Two bundles of app.jsx: bundle.js with React 19 (createRoot) and bundle17.js with React 17 and a
// legacy ReactDOM.render root, the way www.npmjs.com renders (state updates flush synchronously).
import * as esbuild from "esbuild";

const common = {
  entryPoints: ["app.jsx"], bundle: true, minify: true, jsx: "automatic", logLevel: "warning",
  define: { "process.env.NODE_ENV": '"production"' },
};
await Promise.all([
  esbuild.build({ ...common, outfile: "bundle.js", alias: { "#root": "./root19.js" } }),
  esbuild.build({
    ...common, outfile: "bundle17.js",
    alias: { "#root": "./root17.js", react: "react-17", "react-dom": "react-dom-17" },
  }),
]);
