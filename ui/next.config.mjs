/**
 * Static export: `next build` writes plain files to out/, which the FastAPI
 * service serves at / next to /api. trailingSlash makes every page a folder
 * with an index.html, which is what the static file server looks for.
 */
const config = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default config;
