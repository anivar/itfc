// Site-wide config: nav structure, footer, and brand metadata.

export const SITE = {
  name: 'IT for Change',
  shortName: 'ITfC',
  tagline: 'Bridging Development Realities and Technological Possibilities',
  domain: 'itforchange.net',
  // Address + contact match the 2026 footer block.
  address:
    "# 1371, First Floor, 31st \"B\" Cross, Jayanagar 4th \"T\" Block, Bangalore, Karnataka - 560041",
  phone: '+91 80 2665 4134',
  mapsUrl:
    'https://www.google.com/maps/dir//1371,+31st+B+Cross+Rd,+4th+T+Block+East,+Tilak+Nagar,+Jayanagar,+Bengaluru,+Karnataka+560011',
  email: 'ITfC(at)ITforChange(dot)net',
  emailHref: 'mailto:ITfC@itforchange.net?subject=Hello',
  social: {
    twitter: 'https://www.twitter.com/itforchange',
    facebook: 'https://www.facebook.com/itforchangeindia/',
    youtube: 'https://www.youtube.com/channel/UCQIHbWMOrI0Hg5pSxjoKGlA',
    instagram: 'https://www.instagram.com/itforchange/',
    newsletter: 'https://eepurl.com/cm1zTr',
  },
  license: {
    name: 'Creative Commons Attribution-ShareAlike 4.0',
    url: 'https://creativecommons.org/licenses/by-sa/4.0/',
  },
} as const;

export type NavItem = {
  label: string;
  href: string;
  children?: NavItem[];
  external?: boolean;
};

// Primary navigation — mirrors the 2026 Drupal main menu (see
// https://web.archive.org/web/20260424201529/itforchange.net).
export const NAV: NavItem[] = [
  {
    label: 'About Us',
    href: '/aboutus',
    children: [
      { label: 'Overview', href: '/aboutus' },
      { label: 'Governing board', href: '/gov-board' },
      { label: 'Leadership', href: '/leadership' },
      { label: 'Team', href: '/team' },
      { label: 'Annual reports', href: '/RightToKnow' },
      { label: 'Policies', href: '/policies' },
      { label: 'Contact us', href: '/contact-Us' },
      { label: 'Join us', href: '/Joinus' },
      { label: 'Intern With Us', href: '/intern-with-us' },
      { label: 'Tenders', href: '/tenders' },
    ],
  },
  {
    label: 'Focus Areas',
    href: '/focus-areas',
    children: [
      { label: 'Development & Democracy', href: '/development-and-democracy' },
      { label: 'Internet Governance', href: '/internet-governance' },
      { label: 'Education', href: '/education' },
      { label: 'Gender', href: '/gender' },
    ],
  },
  { label: 'Publications', href: '/resources_all' },
  {
    label: 'What We Do',
    href: '/what-we-do',
    children: [
      { label: 'Research', href: '/research' },
      { label: 'Advocacy', href: '/advocacy' },
      { label: 'Field Projects', href: '/field-projects' },
      { label: 'Courses & Curriculum', href: '/courses-curriculum' },
      { label: 'Networks', href: '/networks' },
      { label: 'Events', href: '/events' },
    ],
  },
  { label: 'Prakriye', href: 'https://itforchange.net/namma-maathu/', external: true },
  { label: 'Donate', href: '/donate' },
];

// Footer "quick links" block from the original.
export const FOOTER_LINKS: NavItem[] = [
  { label: 'Site map', href: '/sitemap' },
  { label: 'Privacy Policy', href: '/privacy' },
];
