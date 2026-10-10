// Kept free of browser-only imports: the Studio route pages run it on the server.

/** Only the user's own app_data images may be handed between Studio pages. */
export function isStudioImagePath(value: string | null | undefined): value is string {
  return !!value && /^\/app_data\/images\/[^?#]+\.(png|jpe?g|webp)$/i.test(value) && !value.includes("..");
}
