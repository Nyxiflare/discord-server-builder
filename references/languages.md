# Building servers in other languages

Set `"language"` in the blueprint (`es`, `pt-BR`, `hi`, `ja`, `ar`, `fr`, `de`, `id`, ...). Then
write **everything** members read in that language: channel and category names, roles, topics,
starter posts, AutoMod `block_message`, welcome screen, onboarding questions and scam phrases.
`assets/templates/creator-community.es.json` is a complete example.

## Rules that apply to every language

- **Write natively; don't translate literally.** Use the names local Discord communities actually
  use ("normas" rather than "reglas-de-la-comunidad"). When unsure, keep it short and common.
- **Text channel names**: Discord lowercases Latin letters and turns spaces into hyphens. It
  removes most ASCII punctuation (`! " # $ % & ' ( ) * + , . / : ; < = > ? @ [ \ ] ^ { | } ~`);
  `validate` warns if a name has any. Letters from any script (accents, Devanagari, kana, kanji,
  Arabic), emojis and decorative separators like `・` or `┃` are fine. Keep names under ~25
  characters so they fit on phones.
- **Voice channels, categories and roles** keep capitals, spaces and punctuation.
- **Placeholders** stay as they are: `{server}`, `{#channel-name}` (use the translated channel
  name), `{@Role Name}`, `{:emoji_name:}`.
- **AutoMod**: add local scam phrases to `scam_words` and local slurs/insults to `blocked_words`.
  Discord's preset lists are mostly English, so the keyword rules do more of the work in other
  languages. Put normal local words that filters catch by mistake in `allowed_words`.
- **Mixed-language communities**: pick the majority language for structure, and add one channel
  per other language (`english`, `español`), not two copies of everything.
- The **preview** (`preview BLUEPRINT`) sets the page language and switches to right-to-left for
  Arabic, Hebrew, Persian and Urdu.

## Per language

| Language | Natural channel names | Tone and conventions |
|---|---|---|
| **Spanish** (`es`) | bienvenida, normas, anuncios, general, presentaciones, off-topic, sorteos, dudas | Use `tú`. "Bienvenid@" or "Te damos la bienvenida" for inclusive greetings. Neutral Latin American wording reaches the most people; say "video" (LatAm) vs "vídeo" (Spain) to match the creator. |
| **Portuguese, Brazil** (`pt-BR`) | boas-vindas, regras, avisos, geral, apresentações, off-topic, sorteios, dúvidas | Informal `você`, warm and playful. "Bate-papo" for casual chat. Brazilians use emojis and "kkk" freely, so a relaxed tone fits. |
| **Hindi** (`hi`) | Most Indian servers mix Hindi and English (Hinglish) in Latin script: welcome, rules, general-chat, gupshup, announcements. Devanagari names (स्वागत, नियम, घोषणाएँ) work but are harder to type. | Use `aap` in rules and `tum` only for very casual servers. Write starter posts in Hindi with common English terms (stream, video, giveaway) left in English. Ask the creator whether their audience writes in Devanagari or Hinglish. |
| **Japanese** (`ja`) | ようこそ, ルール, お知らせ, 雑談, 自己紹介, 質問, 作品投稿 | Polite です/ます form in rules and announcements; casual in chat channel topics. Short names. Japanese servers often prefix with emoji (📢｜お知らせ); `｜` (full-width bar) is fine. |
| **Arabic** (`ar`) | الترحيب, القوانين, الإعلانات, الدردشة-العامة, التعريف-بنفسك | Modern Standard Arabic for rules and announcements; the creator's dialect (Egyptian, Gulf, Levantine) for casual topics if they use it. Discord shows Arabic right-to-left automatically; the preview does too. Put emojis at the **start** of names so they don't jump around in mixed-direction text. |
| **French** (`fr`) | bienvenue, règles, annonces, discussion, présentations, hors-sujet, entraide | `Tu` in gaming and creator servers, `vous` in professional/business ones. French typography wants a space before `! ? :` in prose, but not in channel names. |
| **German** (`de`) | willkommen, regeln, ankündigungen, allgemein, vorstellungen, offtopic, hilfe | `Du` for almost all communities (`Sie` only for formal business). Compound words get long: prefer `regeln` over `serverregeln`. Germany's laws on giveaways and data are strict: mention it in the giveaway caveat. |
| **Indonesian** (`id`) | selamat-datang, peraturan, pengumuman, obrolan, perkenalan, tanya-jawab, giveaway | Friendly `kamu`; `kalian` for the whole group. English loanwords (giveaway, stream, mabar for "main bareng") are normal. |

## Checklist before applying

1. `validate` shows no warnings about removed characters in channel names.
2. Every `{#...}` placeholder uses the translated channel name.
3. The AutoMod `block_message` and the onboarding questions are in the same language.
4. Open the `preview` and read it as a member would: is anything still in English by accident?
