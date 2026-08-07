# draw.io figure sources

[draw.io](https://www.drawio.com/) diagrams embedded in the documentation. The
`.drawio` file is the only thing you edit; the rendered SVGs are produced by the
`drawio` Sphinx extension (`docs/source/_ext/drawio.py`) and cached in
`_drawio_cache/`.

## Using a diagram

```markdown
:::{drawio-figure} figs/drawio/fabulous_ecosystem.drawio
:alt: What the diagram shows, for screen readers
:width: 100%

Caption.
:::
```

The directive takes the same options as `figure` (`alt`, `width`, `align`,
`name`, `figclass`, ...). The path is resolved like any other image path, so it
is relative to the document unless it starts with `/`.

Every diagram is rendered twice, once per page theme. Furo's `only-light` and
`only-dark` classes show the matching one, honouring both the theme toggle and
the reader's `prefers-color-scheme`. Builders with no theme to switch on (LaTeX,
EPUB) only ever get the light variant. You do not have to draw the dark version:
draw.io derives one for every colour, and the extension resolves both out of a
single export. Where that derivation gives a poor result, the dark colour can be
pinned by hand — see below.

## Pinning the dark colours

draw.io derives its dark colours by keeping the hue and inverting the *relative
luminance*: a fill at luminance 0.88 comes back at 0.12. Pale fills are the
normal thing to draw with, and 0.12 is too dark to carry any hue, so a palette
that is perfectly legible in light mode arrives in dark mode as five shades of
the same near-black.

There is no fixing that from the diagram. `darkFillColor` and its siblings are
ignored on export, and the only other lever — making the light colours darker so
their counterparts come out lighter — changes the light diagram to fix the dark
one.

So the dark colours can be pinned by hand instead. Put a `<diagram>.dark.toml`
next to the source, mapping each light colour to the dark colour that should
replace it:

```toml
# user input
"#d5e8d4" = "#21501e"
"#82b366" = "#38ab32"
```

Either side may be `#rgb`, `#rrggbb` or `rgb(r, g, b)`. Colours the table does
not mention keep whatever draw.io derived, which is what you want for text and
greys — it handles those well. A colour the diagram does not use is an error,
not a silent no-op, so the table cannot quietly drift away from the diagram.

Two things worth knowing when picking the dark values:

- **Even luminance beats even lightness.** Blue and violet carry far less
  luminance than green at the same HSL lightness, so a set that looks even on
  paper renders ragged, some boxes twice as bright as others. Pin every fill to
  one luminance and every stroke to another.
- **Neighbouring hues converge.** Orange and yellow are thirteen degrees apart
  and both land on brown. Spread the hues out, or the categories stop being
  distinguishable however good each colour is on its own.

The table is hashed with the diagram, so editing it re-renders exactly as
editing the diagram does.

## Editing a diagram

Edit the `.drawio` and commit it. The `render-drawio` pre-commit hook re-exports
any diagram whose renders no longer match, drops the superseded files, and stages
the new ones with the diagram, so the two never part company. Building the docs
re-exports too, if you get there first.

Re-render everything, for instance after changing `drawio_border`:

```bash
task docs-build FIGS=force
```

The renders are keyed by the diagram alone, so a change to the options below is
the one edit neither the hook nor a plain build can notice for you.

## Why the renders are committed

Exporting needs the draw.io CLI, which is an Electron app and an unreasonable
thing to install on Read the Docs or in CI. Committing the renders means only
the person editing a diagram needs draw.io; everyone else builds from the cache.
The cache is keyed by a hash of the source, so it cannot silently go stale — a
build that finds no matching render and no draw.io fails with a message telling
you to install draw.io and rebuild.

The hash is taken over the source with line endings, trailing whitespace and the
final newline normalised. draw.io saves without a trailing newline and
pre-commit's `end-of-file-fixer` adds one, which would otherwise retire a render
that is still correct and break the docs build everywhere draw.io is missing.

## Configuration

| `conf.py` value | Default | Purpose |
| --- | --- | --- |
| `drawio_binary_path` | auto-detected | Path to the draw.io CLI. Also read from `$DRAWIO_BINARY`, then `drawio` on `PATH`, then the macOS app bundle. |
| `drawio_border` | `12` | Border left around the diagram, in diagram units. |
| `drawio_export_timeout` | `120` | Seconds to wait for an export. |

On macOS the CLI lives inside the app bundle
(`/Applications/draw.io.app/Contents/MacOS/draw.io`) and is found automatically.
On Linux, install [drawio-desktop](https://github.com/jgraph/drawio-desktop) so
that `drawio` is on `PATH`; a headless machine also needs `xvfb-run`.
