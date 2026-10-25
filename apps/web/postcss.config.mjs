/** Tailwind CSS v4 — the PostCSS plugin is the whole pipeline.
 *  No `tailwindcss` entry and no `autoprefixer`: v4 handles both internally,
 *  and adding them is what breaks a v4 build. */
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
