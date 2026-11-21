# Aurion: UI Design Guide

This guide explains how Aurion looks, why its interface works this way, and how to extend it consistently. Each section begins with the user experience, then gives the implementation details behind it.

Aurion is a vehicle sales assistant. Its visual direction combines a spacious, Gemini-inspired conversation layout with smoky charcoal glass, distant colored light, and a simple white A as its identity.

## 1. Start with the conversation

The interface should help someone ask a question, read an answer, and understand what happens next. Visual effects support those tasks. They should never compete with them.

Three principles guide the design:

- **Keep the next action clear.** The message field is wide and easy to find. A white send button becomes available when a message can be sent.
- **Use depth to organize information.** The conversation is the main workspace. The activity dashboard and floating note are supporting surfaces.
- **Give color a purpose.** Charcoal and gray provide structure. RGB mist adds atmosphere to the application background. The logo stays monochrome. Status colors explain system conditions.

An empty conversation stays open and quiet. A centered greeting reads **Hello there.** followed by **Aurion, at your service.** A smaller gray line underneath asks **What would you like to drive today?** The tone is courteous and composed, like a modern English butler: welcoming, direct, and free of archaic language. The greeting disappears once the conversation contains messages. There are no starter cards, suggestion chips, follow-up buttons, or EMI calculator. The input placeholder remains **Ask Aurion anything**.

## 2. Color: charcoal with controlled warmth

Dark mode is the default. The foundation is neutral charcoal, with soft white text and muted gray controls. Several nearby shades of black create separation without heavy outlines.

Transparency is part of the palette. For example, `rgb(26 26 26 / 0.66)` means charcoal at 66% opacity. The remaining transparency allows the background light to influence the visible color.

### Core values

| Role | Current dark-theme value | Purpose |
| --- | --- | --- |
| Page foundation | `#101010` | A calm, nearly black canvas |
| Chat surface | `rgb(26 26 26 / 0.66)` | Main conversation layer |
| Sidebar surface | `rgb(32 32 32 / 0.72)` | Separate activity from conversation |
| Floating note | `rgb(38 38 38 / 0.92)` | Keep explanatory text legible |
| User message | `#353535`, text `#ededed` | Distinguish the user's words |
| Main text | Generally `#f0f0f0` | Comfortable reading |
| Secondary text | Generally `#a3a3a3` to `#b5b5b5` | Supporting information |
| Available send action | White, arrow `#777777` | Make the next action visible |
| Logo letter | White, `#ffffff` | Clear, minimal brand signature |

The light theme uses neutral gray and translucent pale surfaces. The layout and component behavior stay consistent across themes. The logo keeps its white letter and charcoal tile in both themes.

Green, amber, and red appear in status feedback. Their meaning comes from the accompanying label or message, so users do not have to interpret color alone.

## 3. Material: light seen through frosted glass

The material should feel like smoky, mist-frozen glass. A surface has enough body to hold readable content, while allowing soft background color to show through.

Four properties create that effect:

1. **Translucent fill** lets some background light through.
2. **Backdrop blur** softens what is behind the panel, like looking through frosted glass.
3. **A faint border or inner highlight** reveals the edge.
4. **A soft shadow** separates the surface from the layer underneath.

Backdrop blur affects the scene behind a panel. It does not blur the panel's text or controls. The RGB mist uses a separate blur on the light itself.

### Surface specifications

| Surface | Backdrop treatment | Shape and detail |
| --- | --- | --- |
| Main chat panel | `blur(28px)` | 28 px corners, faint border |
| Activity sidebar | `blur(24px)` | 28 px corners, translucent fill |
| Header | `blur(16px)` | Subtle tint within the chat panel |
| Developer note | `blur(28px) saturate(140%)` | Rounded floating panel with shadow |
| Message composer | `blur(24px) saturate(150%)` | 28 px corners, inner highlight and shadow |

In dark mode, the composer fill blends from `rgb(58 58 58 / 0.75)` to `rgb(38 38 38 / 0.65)`. Most dark surface borders use white at roughly 5% to 15% opacity.

When adjusting the material, check the result over the brightest mist as well as the darkest background. A fill that looks clear on plain black may become difficult to read over color. Increase surface opacity when readability needs more separation.

## 4. Atmosphere: distant RGB mist

Red, green, and blue light begins around the center and spreads outward. The intended impression is light arriving from far away through fog: broad, soft, and without visible edges.

The effect uses overlapping radial gradients. A radial gradient fades outward from a center point; an elliptical shape makes the light feel more natural than three identical circles.

| Light | Inner color | Center within the mist layer |
| --- | --- | --- |
| Red | `rgb(239 75 85 / 0.5)` | 36% horizontal, 48% vertical |
| Green | `rgb(67 203 135 / 0.42)` | 53% horizontal, 39% vertical |
| Blue | `rgb(72 126 245 / 0.55)` | 65% horizontal, 56% vertical |

Each gradient passes through a weaker outer color before fading to transparency. The background layer extends 12% beyond its container on every side and uses `blur(clamp(30px, 5vw, 80px))`. This keeps the glow soft at different screen sizes and helps conceal its boundaries.

The layer sits behind the interface and ignores pointer events. It should remain decoration rather than an interactive object.

### Motion and depth

The mist scales from `0.84` to `1.16`, while opacity moves from `0.65` to `1`. Its origin is at `50% 48%`. Each direction takes 24 seconds, easing in and out and alternating continuously.

The slow change creates a sense of distance without asking for attention. With reduced motion enabled, the mist stays still at 85% opacity. Other animations and transitions are also minimized.

## 5. Identity: the white A

Aurion's mark is a white **A** inside a simple charcoal tile. Its background uses the same charcoal tones as the dark message field. The logo contains no colored mist, glow, or decorative rim; its clarity balances the atmospheric application background.

The letter has a bold geometric sans-serif construction: angled legs, a flat apex, and a clear counter, the small space inside the A. These features give it a precise automotive character and help it remain recognizable at small sizes.

The A is drawn as a vector path. It does not depend on a font being installed, so its shape stays consistent across devices.

| Property | Specification |
| --- | --- |
| Artwork coordinates | `64 × 64` SVG view box |
| Tile foundation | Charcoal gradient, `#3a3a3a` to `#262626` |
| Letter fill | White, `#ffffff` |
| Surface finish | Simple neutral fill, without colored effects |
| Typical display sizes | 40 px in the sidebar, 32 px in chat |

The same artwork appears in the sidebar, assistant avatars, and browser favicon. Its charcoal background and white A remain consistent in light, dark, and system themes. Preserve that identity when creating new placements.

## 6. Layout: a clear workspace at every size

The application fills the viewport. Small outer spacing gives the rounded panels room to stand apart. The desktop sidebar and chat panel have a 12 px gap; outer padding is 8 px on small screens and 12 px from the small breakpoint upward.

The execution dashboard is 288 px wide on desktop and 320 px at the extra-large breakpoint. Below the medium breakpoint, it opens as a drawer over a dimmed, blurred backdrop. The header provides the drawer control.

The chat panel has three functional areas:

- **Header:** Aurion identity, call usage, reset, developer note, service check, and theme selection.
- **Conversation:** A scrolling reading area with a centered maximum content width of 896 px.
- **Composer:** A nearly full-width input anchored below the conversation.

The current Tailwind breakpoints used here are 640 px for small, 768 px for medium, and 1280 px for extra-large layouts. The header can wrap its controls when space is limited.

Major panels and the composer use 28 px corner radii. Cards and message bubbles generally use 24 px radii. Utility actions use pills or circles. Repeating these shapes makes the interface feel related without giving every element the same visual weight.

## 7. Typography: readable first

Text size, weight, and spacing establish visual hierarchy: they tell the reader what to notice first. Use stronger emphasis for identity and important content, and quieter styles for timestamps and supporting information.

| Text role | Current treatment |
| --- | --- |
| Header wordmark | 20 to 24 px, medium weight |
| Chat content | Approximately 15 px |
| Message input | 16 px, 24 px line height |
| Supporting labels | Generally 11 to 12 px |
| Markdown paragraphs | Line height `1.65` |

The font stack prefers Inter, then uses system sans-serif fonts when Inter is unavailable. Declaring Inter in CSS does not itself download the font. Lucide icons provide a consistent outline style for controls.

Keep long answers easy to scan with short paragraphs, meaningful headings, and tables when comparison helps. Let content determine the formatting.

## 8. The composer: one clear place to begin

The composer combines the text area and a circular send control on one frosted surface. Horizontal margins are 12 px on small screens and 24 px from the small breakpoint upward. The initial height is approximately 58 px including its border and padding, with rounded ends.

The placeholder is **Ask Aurion anything**. The text area starts at one line, grows in whole 24 px line increments, and scrolls internally after eight lines. Width changes trigger a new height calculation so wrapping continues to work after resizing.

### Interaction states

| State | Behavior and appearance |
| --- | --- |
| Empty or whitespace only | Subdued, disabled send button |
| Valid text and sending available | White button with a gray upward arrow |
| Hover on available send | Slightly softer white fill |
| Waiting for a response | Send control becomes a stop button |
| Cooldown or exhausted budget | Sending remains unavailable; explanatory feedback appears |
| Message exceeds its length limit | Error styling and a visible explanation |

Enter sends a valid message. Shift + Enter inserts a new line. Enter during input-method composition does not submit. The slash shortcut focuses the composer when the user is outside a text input; Escape stops a pending reply.

The active button depends on whether sending is allowed, not simply on whether any characters are present. This keeps visual feedback aligned with the actual action.

## 9. Messages and supporting surfaces

User messages align to the right in rounded charcoal bubbles. Assistant replies use an open layout with a small Aurion avatar, giving longer answers more reading space. The same open treatment applies while a response streams in.

Copy, retry, and jump-to-latest controls support reading and recovery. They should stay secondary to the message. Status text and errors explain what is happening and what the user can do next.

The activity dashboard presents execution runs in softly filled cards. Its signal icons are white in both the dashboard heading and empty activity card, including the mobile drawer. It helps users inspect query progress, tool activity, and results without interrupting the main conversation. The developer note uses a floating glass panel for optional explanatory content.

## 10. Accessibility and review criteria

The current interface includes accessible names for icon controls, visible keyboard focus outlines, textual status feedback, and reduced-motion behavior. Decorative mist does not intercept clicks. Theme selection is stored locally under `aurion.theme`, with dark mode as the fallback.

These choices support accessibility, but they are not a claim that every state has passed an accessibility audit. Review the actual rendered interface, especially where translucent layers overlap.

Before accepting a visual change, check:

- Text and controls remain readable over the brightest background colors. Aim for WCAG AA contrast: 4.5:1 for normal text and 3:1 for large text; relevant control boundaries and visual indicators should meet 3:1.
- Keyboard users can identify focus, activate controls, and use the composer.
- Status and error messages explain their meaning without relying on color alone.
- The layout works on narrow screens, at enlarged text sizes, and with long messages.
- Reduced motion removes the spreading animation.
- Light and dark themes preserve clear hierarchy, while the monochrome logo stays consistent.
- Where backdrop blur is unavailable, surface fills still provide usable separation.

These are acceptance criteria for future reviews. Contrast, zoom behavior, and assistive-technology behavior require verification in the browser.

## 11. Where to make changes

| Area | Source |
| --- | --- |
| Palette, glass, mist, focus, motion | [index.css](../frontend/src/index.css) |
| Overall layout and floating note | [App.tsx](../frontend/src/App.tsx) |
| Composer sizing and send states | [Composer.tsx](../frontend/src/components/Composer.tsx) |
| Header controls | [ChatHeader.tsx](../frontend/src/components/ChatHeader.tsx) |
| Dashboard and responsive drawer | [Sidebar.tsx](../frontend/src/components/Sidebar.tsx) |
| Message appearance and avatars | [MessageBubble.tsx](../frontend/src/components/MessageBubble.tsx) |
| Conversation scrolling and streaming | [MessageList.tsx](../frontend/src/components/MessageList.tsx) |
| Shared logo placement | [AurionLogo.tsx](../frontend/src/components/AurionLogo.tsx) |
| Logo artwork and browser icon | [favicon.svg](../frontend/public/favicon.svg) |
| Theme persistence and system preference | [useTheme.ts](../frontend/src/hooks/useTheme.ts) |
| Initial theme before React loads | [index.html](../frontend/index.html) |

When extending Aurion, reuse the existing palette, surface treatments, and component behavior first. Keep the conversation clear, the light diffuse, and the monochrome identity consistent.
