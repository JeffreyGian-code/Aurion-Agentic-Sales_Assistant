# Aurion UI Design

## Design direction

Aurion uses a Gemini-inspired layout with smoky charcoal surfaces, generous curves, and frosted glass. The experience should feel calm, spacious, and atmospheric. Soft light sits behind the interface, while text and controls remain crisp and readable.

Dark mode is the default. A neutral gray light theme and a system theme option are also available. Theme selection is stored locally under `aurion.theme`.

## Color palette

The main interface uses neutral grays rather than blue-tinted blacks. Color comes primarily from the background mist and functional status indicators.

| Element | Dark theme treatment |
| --- | --- |
| Application background | Smoky black, `#101010` |
| Chat panel | Charcoal, `rgb(26 26 26 / 0.66)` |
| Activity sidebar | Charcoal, `rgb(32 32 32 / 0.72)` |
| Floating note | Dark gray, `rgb(38 38 38 / 0.92)` |
| User message | `#353535` with `#ededed` text |
| Primary text | Soft white, generally `#f0f0f0` |
| Secondary text and icons | Muted gray, generally `#a3a3a3` to `#b5b5b5` |
| Active send button | White with a `#777777` arrow |

Green, amber, and red retain their functional roles for service health, waiting states, limits, and errors.

## Material: smoky frosted glass

Panels combine translucent fills, background blur, faint borders, and soft shadows. The result should resemble mist-frozen glass with gentle depth and subdued reflections.

- The chat panel uses a 28 px backdrop blur.
- The sidebar uses a 24 px backdrop blur.
- The header uses a 16 px backdrop blur.
- The developer note uses a 28 px blur with 140% saturation.
- The composer uses a 24 px blur with 150% saturation, a subtle inner highlight, and a soft shadow.

In dark mode, the composer blends from `rgb(58 58 58 / 0.75)` to `rgb(38 38 38 / 0.65)`. Surface boundaries stay faint, with white borders typically between 5% and 15% opacity. The content should remain more prominent than the glass effect.

## RGB mist and depth

Three large, overlapping radial gradients create the impression of distant light spreading through fog:

| Light | Main color | Position within the mist layer |
| --- | --- | --- |
| Red | `rgb(239 75 85 / 0.5)` | Left of center, 36% / 48% |
| Green | `rgb(67 203 135 / 0.42)` | Above center, 53% / 39% |
| Blue | `rgb(72 126 245 / 0.55)` | Right and below center, 65% / 56% |

Each light fades through a weaker outer color into transparency. A responsive blur between 30 and 80 px removes hard edges. The layer extends beyond the screen and sits behind the translucent panels, so the colors appear diffused through the material.

The mist slowly expands from 84% to 116% scale around a central origin, with opacity moving from 65% to 100%. Each direction takes 24 seconds with an ease-in-out transition, alternating continuously. This gives the light a distant, spreading feel. Reduced-motion preferences replace the animation with a static mist layer.

## Layout and shape

The application fills the viewport, with small outer margins and a 12 px gap between the desktop sidebar and chat panel. Major panels have 28 px corner radii. Cards and message bubbles use generous rounded corners; utility controls and the send button use pill or circular shapes.

The execution dashboard occupies a 288 px sidebar on desktop, increasing to 320 px on wide screens. On smaller screens, it opens as a drawer over a dimmed, blurred backdrop. The chat panel remains the main workspace.

The header holds the Aurion wordmark, call usage, conversation reset, developer note, service check, and theme controls. The conversation scrolls independently above the composer. The empty conversation stays visually open, with no starter cards, suggestion chips, or EMI calculator.

## Typography and iconography

The font stack begins with Inter and falls back to system sans-serif fonts. Text uses restrained weights and clear size differences: the Aurion wordmark is 20 to 24 px, chat content is approximately 15 px, and the composer text is 16 px with a 24 px line height.

Lucide icons provide simple line-based controls. A sparkles icon identifies Aurion, set against a neutral gray gradient. Small labels and timestamps use muted grays to keep the conversation prominent.

## Composer behavior

The composer spans nearly the full chat panel width, with 12 to 24 px horizontal margins. Its 28 px radius gives the initial single-line field rounded ends. The text area and circular send button share one horizontal surface.

- Empty placeholder: **Ask Aurion anything**.
- The field starts at one line and grows one line at a time as text wraps or new lines are added.
- After eight lines, the text area scrolls internally.
- Resizing the available width recalculates the field height.
- Enter sends the message; Shift + Enter inserts a new line.
- When a valid message can be sent, the button is white with a gray upward arrow. Its hover fill is a slightly softer white.
- An empty or blocked input uses the subdued disabled button treatment.
- While awaiting a reply, the send control becomes a stop button.
- Limits, cooldowns, and validation feedback appear when relevant.

## Conversation styling

User messages sit in rounded charcoal bubbles aligned to the right. Assistant replies use an open layout with a small Aurion avatar and readable text, allowing longer answers to breathe. Copy and retry controls remain available where applicable. Follow-up suggestion buttons are absent.

The activity dashboard uses softly filled rounded cards for execution traces. The developer note floats above the chat as a frosted panel. These supporting surfaces share the same neutral palette and rounded geometry.

## Interaction and accessibility

Hover feedback is subtle, using changes in fill and text color. Buttons, links, and expandable summaries have visible keyboard focus outlines. Icon controls retain accessible labels. Status feedback uses text alongside color, and decorative mist ignores pointer input.

Motion remains gentle. Reduced-motion settings stop the spreading mist and minimize other transitions and animations.

## Implementation references

- [Global palette, surfaces, mist, and motion](../frontend/src/index.css)
- [Application layout](../frontend/src/App.tsx)
- [Composer and send button](../frontend/src/components/Composer.tsx)
- [Header controls](../frontend/src/components/ChatHeader.tsx)
- [Activity dashboard](../frontend/src/components/Sidebar.tsx)
- [Message appearance](../frontend/src/components/MessageBubble.tsx)
- [Theme selection](../frontend/src/hooks/useTheme.ts)

Future UI changes should preserve the charcoal foundation, diffuse RGB light, frosted surfaces, rounded geometry, and uncluttered conversation area.
