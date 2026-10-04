import registry from '../data/platform-logos.json' with { type: 'json' };

// Stable IDs and aliases live with the provenance metadata. Daily content only
// supplies a platform name; it never needs to download or choose a logo.
const normalize = (name: string) => name.normalize('NFKC').toLocaleLowerCase('en-US').replace(/[\s._/()（）-]+/g, '');
const lookup = new Map<string, (typeof registry)[number]>();
for (const platform of registry) {
  for (const name of [platform.id, platform.name, ...platform.aliases]) {
    const key = normalize(name);
    const existing = lookup.get(key);
    if (existing && existing.id !== platform.id) throw new Error(`Ambiguous platform alias: ${name}`);
    lookup.set(key, platform);
  }
}

export const PLATFORM_LOGO: Record<string, string> = Object.fromEntries(registry.map((p) => [p.name, p.file]));
export const FALLBACK_LOGO = "/logos/platform-generic.svg";
export function registeredLogoFor(platform: string): string | undefined {
  return lookup.get(normalize(platform))?.file;
}

// New names must remain renderable while their official logo is being registered.
export function logoFor(platform: string): string {
  return registeredLogoFor(platform) ?? FALLBACK_LOGO;
}
