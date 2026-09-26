Voici la checklist transformée en plan d'action exécutable, réordonnée par priorité de lancement plutôt que par l'ordre du reel (qui était aléatoire).

## Avant de commencer

Donne d'abord le contexte à Claude une seule fois, sinon tu vas le répéter 20 fois :

```
Voici mon site : [stack, framework, hébergeur, type de site, public FR/UE ?].
Est-ce qu'il y a collecte de données perso (formulaire, compte, analytics, paiement) ?
Réponds par un audit, pas par du code, tant que je ne te le demande pas.
```

Si ton projet a un `CLAUDE.md`, mets-y le stack + l'URL de prod : tous les prompts ci-dessous deviennent plus précis.

## Priorisation

| Niveau | Points | Règle |
|---|---|---|
| 🔴 Bloquant | 1, 2, 3, 4, 5, 18 | Ne pas mettre en ligne sans ça — risque légal ou faille |
| 🟠 Avant indexation | 6, 7, 8, 9, 10, 15, 16, 17 | À faire avant que Google passe, sinon tu corriges à retardement |
| 🟡 Avant trafic réel | 11, 12, 13, 14, 20 | Impacte conversion et SEO, mais rattrapable |
| 🟢 Jour J | 19 | À poser juste avant l'ouverture pour avoir des données propres dès le début |

---

## Phase 1 — Légal & sécurité 🔴

| # | Action | Vérification |
|---|---|---|
| 3 | Sortir toute clé d'API du front-end → variables d'env côté serveur / route proxy | `grep -rE "sk-\|api[_-]?key\|secret" dist/ build/` ne doit rien sortir |
| 4 | Forcer HTTPS + redirection 301 depuis HTTP, activer HSTS | Tester `http://` → doit rediriger |
| 1 | Page politique de confidentialité (RGPD) : finalité, base légale, durée, droits, contact DPO | Lien accessible depuis le footer de **chaque** page |
| 2 | Page CGU / mentions légales (obligatoire en France, même pour un site vitrine) | Idem footer |
| 5 | Bannière cookies avec **consentement préalable** — refuser doit être aussi simple qu'accepter | Ouvrir en navigation privée : aucun cookie non essentiel avant clic |
| 18 | Anti-spam sur les formulaires : honeypot + rate limiting (et captcha seulement si nécessaire) | Soumettre 10 fois d'affilée → doit bloquer |

Prompt utile :

```
Audite mon code : est-ce qu'une clé d'API, un token ou un secret est exposé côté client ?
Liste chaque occurrence avec le fichier et la ligne, puis propose la correction.
```

⚠️ Point 5 : le piège classique est de charger le script d'analytics **avant** le consentement. La bannière ne sert à rien si le cookie est déjà posé — vérifie l'ordre de chargement, pas juste la présence de la bannière.

## Phase 2 — SEO & indexation 🟠

| # | Action | Vérification |
|---|---|---|
| 6 | `<title>` unique (50–60 car.) + `meta description` (150–160 car.) par page | Voir le source de 3 pages différentes |
| 7 | Image Open Graph 1200×630 + balises `og:` et `twitter:card` | opengraph.xyz ou le debugger de la plateforme |
| 8 | Favicon multi-formats (`.ico`, 180×180 Apple, 512×512 PWA) | Onglet du navigateur + ajout à l'écran d'accueil mobile |
| 10 | Attribut `alt` descriptif sur toutes les images (vide `alt=""` si décoratif) | Point commun avec le 13 : c'est de l'accessibilité autant que du SEO |
| 9 | `sitemap.xml` généré + `robots.txt` qui le référence | `curl -I tonsite.com/sitemap.xml` → 200 |
| 16 | Réparer les liens cassés (internes **et** externes) | Commande ci-dessous |

```bash
npx linkinator https://tonsite.com --recurse --skip "linkedin|twitter"
```

Prompt utile :

```
Passe en revue chaque page et propose un title + meta description uniques,
optimisés pour l'intention de recherche. Signale les doublons et les pages sans balise.
```

## Phase 3 — Performance 🟡

| # | Action | Cible |
|---|---|---|
| 11 | Convertir les images en WebP/AVIF, redimensionner à la taille d'affichage réelle, `loading="lazy"` hors du viewport initial | Aucune image > 200 Ko |
| 12 | Core Web Vitals | LCP < 2,5 s · CLS < 0,1 · INP < 200 ms |

```bash
npx lighthouse https://tonsite.com --view --preset=desktop
```

Relance en `--preset=mobile` : c'est ce score-là que Google utilise pour le classement.

## Phase 4 — UX & accessibilité 🟡

| # | Action | Vérification |
|---|---|---|
| 14 | Responsive réel : tester 375 px, 768 px, 1440 px | Aucun scroll horizontal, zones tactiles ≥ 44 px |
| 13 | Contraste texte/fond ≥ 4,5:1 (3:1 pour le texte large) | Onglet Accessibility de Lighthouse |
| 15 | Page 404 personnalisée avec navigation de secours | Visiter `tonsite.com/nimportequoi` |
| 17 | Validation des formulaires **côté serveur** (pas seulement côté client) + messages d'erreur explicites | Soumettre avec JS désactivé |
| 20 | Un seul CTA principal par page, répété si la page est longue | Relire chaque page : quelle est l'action unique attendue ? |

Prompt utile :

```
Analyse cette page : quel est le CTA principal, et est-ce qu'un autre élément
lui fait concurrence visuellement ? Propose une hiérarchie claire.
```

## Phase 5 — Jour du lancement 🟢

| # | Action |
|---|---|
| 19 | Installer l'analytics (Plausible/Matomo si tu veux éviter la complexité RGPD, GA4 sinon) — **après** la bannière cookies du point 5, et conditionné au consentement |

Puis : soumettre le sitemap à Google Search Console, et refaire un Lighthouse sur la prod pour avoir une mesure de référence.

---

## Séquence recommandée

1. **Session 1** — Phase 1 en entier. Tant que ce n'est pas vert, pas de mise en ligne.
2. **Session 2** — Phases 2 + 4, elles se recoupent (le point 10 sert aux deux).
3. **Session 3** — Phase 3, en mesurant avant/après pour ne pas optimiser à l'aveugle.
4. **Jour J** — Phase 5, puis Search Console.

Deux remarques sur la liste d'origine : les points 10 et 13 relèvent de l'accessibilité, sujet que le reel ne nomme jamais alors que c'est une obligation légale pour certains sites en France — si tu es concerné (service public, entreprise > 250 M€ de CA), le RGAA va bien au-delà de ces deux points. Et le point 18 « anti-spam » est trop vague pour être actionnable tel quel : j'ai tranché pour honeypot + rate limiting, qui couvre la majorité des cas sans dégrader l'expérience.

Si tu me dis de quel site il s'agit — `website_reservation` ou un autre — je peux ouvrir le projet et transformer ça en audit réel, avec les points déjà faits cochés et les fichiers exacts à modifier.