import type { HelpSection } from "@/app/(presentation-generator)/services/api/help";

// The built-in help (messages/*.json → help.sections), shown until an
// administrator saves their own in Admin → Help. The official Presenton
// documentation exists only in English; the links lead there.
export const DOCS_URL = "https://docs.presenton.ai/help";
const TROUBLESHOOTING_URL = "https://docs.presenton.ai/archive/v0.9.0-beta/troubleshooting";

export type BuiltinProblem = { problem: string; solution: string };

export const BUILTIN_SECTIONS = [
  { id: "start", kind: "steps", docs: DOCS_URL },
  { id: "language", kind: "list" },
  { id: "templates", kind: "list", docs: DOCS_URL },
  { id: "generation", kind: "problems", docs: `${TROUBLESHOOTING_URL}/generation` },
  { id: "content", kind: "problems", docs: `${TROUBLESHOOTING_URL}/content-and-media` },
  { id: "export", kind: "problems", docs: `${TROUBLESHOOTING_URL}/editing-and-export` },
  { id: "hosting", kind: "problems", docs: `${TROUBLESHOOTING_URL}/hosting` },
  { id: "support", kind: "steps" },
] as const;

type HelpTranslator = {
  (key: string): string;
  raw: (key: string) => unknown;
};

/** The built-in help as editable sections (Markdown), to start editing from. */
export function builtinHelpSections(t: HelpTranslator): HelpSection[] {
  const intro: HelpSection = {
    id: "intro",
    title: "",
    body: t("intro"),
    files: [],
    videos: [],
  };
  return [
    intro,
    ...BUILTIN_SECTIONS.map((section) => {
      const lines: string[] = [];
      if (section.kind === "steps") {
        (t.raw(`sections.${section.id}.steps`) as string[]).forEach((step, index) =>
          lines.push(`${index + 1}. ${step}`),
        );
      } else if (section.kind === "list") {
        (t.raw(`sections.${section.id}.items`) as string[]).forEach((item) => lines.push(`- ${item}`));
      } else {
        (t.raw(`sections.${section.id}.items`) as BuiltinProblem[]).forEach((item) =>
          lines.push(`**${item.problem}**  \n${item.solution}`, ""),
        );
      }
      if ("docs" in section) {
        lines.push("", `[${t("moreInDocs")}](${section.docs})`);
      }
      return {
        id: section.id,
        title: t(`sections.${section.id}.title`),
        body: lines.join("\n").trim(),
        files: [],
        videos: [],
      };
    }),
  ];
}
