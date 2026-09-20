import type { ChatStreamTrace } from "../../../services/api/chat";
import type { AssistantActivity } from "./chat-types";

type Translator = (key: string) => string;

// Maps the backend tool id to a translation key under chat.activity.tool.*
const TOOL_LABEL_KEYS: Record<string, string> = {
  addOutline: "activity.tool.addOutline",
  updateOutline: "activity.tool.updateOutline",
  deleteOutline: "activity.tool.deleteOutline",
  addNewSlide: "activity.tool.addNewSlide",
  addNewSlideLayout: "activity.tool.addNewSlideLayout",
  getAvailableLayouts: "activity.tool.getAvailableLayouts",
  getTemplateSummary: "activity.tool.getTemplateSummary",
  readSourceDocuments: "activity.tool.readSourceDocuments",
  searchSlide: "activity.tool.searchSlide",
  getSlideAtIndex: "activity.tool.getSlideAtIndex",
  saveSlide: "activity.tool.saveSlide",
  updateSlide: "activity.tool.updateSlide",
  deleteSlide: "activity.tool.deleteSlide",
  addElement: "activity.tool.addElement",
  updateElement: "activity.tool.updateElement",
  deleteElement: "activity.tool.deleteElement",
  addComponent: "activity.tool.addComponent",
  createComponent: "activity.tool.createComponent",
  updateComponent: "activity.tool.updateComponent",
  deleteComponent: "activity.tool.deleteComponent",
  getPresentationTheme: "activity.tool.getPresentationTheme",
  setPresentationTheme: "activity.tool.setPresentationTheme",
  generateAssets: "activity.tool.generateAssets",
};

export const MUTATING_TOOLS = new Set([
  "addOutline",
  "updateOutline",
  "deleteOutline",
  "addNewSlide",
  "addNewSlideLayout",
  "saveSlide",
  "updateSlide",
  "deleteSlide",
  "addElement",
  "updateElement",
  "deleteElement",
  "addComponent",
  "createComponent",
  "updateComponent",
  "deleteComponent",
  "setPresentationTheme",
]);

// Read/open traces can happen ahead of edits and would make follow mode jumpy.
export const SLIDE_FOCUS_TOOLS = new Set([
  "addNewSlide",
  "addNewSlideLayout",
  "saveSlide",
  "updateSlide",
  "deleteSlide",
  "addElement",
  "updateElement",
  "deleteElement",
  "addComponent",
  "createComponent",
  "updateComponent",
  "deleteComponent",
]);

export const SLIDE_FOCUS_STATUSES = new Set(["start"]);
export const MIN_SLIDE_FOCUS_DWELL_MS = 700;

const getToolLabel = (tool: string | undefined, t: Translator) => {
  if (!tool) return "";
  const key = TOOL_LABEL_KEYS[tool];
  return key ? t(key) : tool;
};

// Keys are the exact lowercased backend messages (matchers, not translated);
// values are translation keys under chat.activity.msg.*
const EXACT_MESSAGE_KEYS: Record<string, string> = {
  "reading deck context": "activity.msg.reviewContext",
  "reading the presentation outline": "activity.msg.readOutline",
  "reading the outline draft": "activity.msg.readOutlineDraft",
  "adding an outline slide": "activity.msg.addOutlineSlide",
  "updating the outline slide": "activity.msg.updateOutlineSlide",
  "deleting the outline slide": "activity.msg.deleteOutlineSlide",
  "reordering outline slides": "activity.msg.reorderOutline",
  "searching relevant slides": "activity.msg.searchRelevant",
  "opening the requested slide": "activity.msg.openSlide",
  "checking available themes": "activity.msg.checkThemes",
  "checking available layouts": "activity.msg.checkLayouts",
  "checking the layout schema": "activity.msg.validateSchema",
  "generating slide assets": "activity.msg.generateAssets",
  "saving the slide": "activity.msg.saveSlide",
  "deleting the slide": "activity.msg.deleteSlide",
  "applying presentation theme": "activity.msg.applyTheme",
  "reading template structure": "activity.msg.readTemplate",
  "reading source documents": "activity.msg.readDocs",
  "opening the requested template slide": "activity.msg.openTemplateSlide",
  "searching template content": "activity.msg.searchTemplate",
  "finding editable elements": "activity.msg.findEditable",
  "updating template content": "activity.msg.updateTemplate",
  "deleting the template component": "activity.msg.deleteComponent",
  "swapping component variant": "activity.msg.swapVariant",
};

const humanizeTraceMessage = (
  message: string,
  tool: string | undefined,
  t: Translator,
) => {
  const trimmed = message.trim();
  if (!trimmed) return "";

  const lower = trimmed.toLowerCase();
  const exactKey = EXACT_MESSAGE_KEYS[lower];
  if (exactKey) return t(exactKey);

  if (lower.startsWith("using tools:")) {
    const toolNames = trimmed
      .slice("using tools:".length)
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean)
      .map((entry) => getToolLabel(entry, t));
    return toolNames.length === 0
      ? t("activity.planningNext")
      : t("activity.choosingBest");
  }
  if (lower.includes("found requested data")) {
    return tool === "getSlideAtIndex"
      ? t("activity.foundSlideDetails")
      : t("activity.foundInfo");
  }
  return trimmed;
};

export const inferStatusState = (
  status: string,
): AssistantActivity["state"] => {
  const normalized = status.trim().toLowerCase();
  if (
    [
      "preparing",
      "thinking",
      "reading",
      "searching",
      "opening",
      "generating",
      "processing",
      "finalizing",
      "saving",
    ].some((term) => normalized.includes(term))
  ) {
    return "running";
  }
  return "info";
};

export const isAbortError = (error: unknown) =>
  (error instanceof DOMException && error.name === "AbortError") ||
  (error instanceof Error &&
    error.message.toLowerCase().includes("aborted") &&
    error.message.toLowerCase().includes("request"));

export const stripBackendContextFromUserMessage = (rawMessage: string) => {
  const message = rawMessage ?? "";
  if (!message.startsWith("UI context:")) return message;

  const marker = "\nUser message:";
  const markerIndex = message.indexOf(marker);
  if (markerIndex === -1) return message;
  return message.slice(markerIndex + marker.length).trimStart();
};

const humanActivityForTool = (
  tool: string | undefined,
  state: "start" | "success",
  t: Translator,
) => {
  const isDone = state === "success";
  switch (tool) {
    case "searchSlide":
      return isDone ? t("activity.act.searchDone") : t("activity.act.searchStart");
    case "getSlideAtIndex":
      return isDone ? t("activity.act.readDone") : t("activity.act.readStart");
    case "addNewSlide":
    case "addNewSlideLayout":
    case "updateElement":
    case "updateComponent":
    case "addElement":
    case "addComponent":
    case "createComponent":
    case "updateSlide":
    case "saveSlide":
      return isDone ? t("activity.act.applyDone") : t("activity.act.applyStart");
    case "deleteComponent":
    case "deleteElement":
    case "deleteSlide":
      return isDone ? t("activity.act.removeDone") : t("activity.act.removeStart");
    case "generateAssets":
      return isDone ? t("activity.act.assetsDone") : t("activity.act.assetsStart");
    case "setPresentationTheme":
      return isDone ? t("activity.act.themeDone") : t("activity.act.themeStart");
    default:
      return isDone ? t("activity.act.defaultDone") : t("activity.act.defaultStart");
  }
};

export const formatTraceActivity = (
  trace: ChatStreamTrace,
  t: Translator,
): Omit<AssistantActivity, "id"> | null => {
  if (typeof trace.message === "string" && trace.message.trim().length > 0) {
    return {
      label: humanizeTraceMessage(trace.message, trace.tool, t),
      kind: trace.kind,
      round: trace.round,
      tool: trace.tool,
      state:
        trace.status === "error"
          ? "error"
          : trace.status === "success"
            ? "success"
            : trace.status === "ready" || trace.status === "info"
              ? "info"
              : "running",
    };
  }
  if (trace.tool && trace.status === "start") {
    return {
      label: humanActivityForTool(trace.tool, "start", t),
      kind: trace.kind,
      round: trace.round,
      tool: trace.tool,
      state: "running",
    };
  }
  if (trace.tool && trace.status === "success") {
    return {
      label: humanActivityForTool(trace.tool, "success", t),
      kind: trace.kind,
      round: trace.round,
      tool: trace.tool,
      state: "success",
    };
  }
  if (trace.tool && trace.status === "error") {
    return {
      label: t("activity.couldNotFinish"),
      kind: trace.kind,
      round: trace.round,
      tool: trace.tool,
      state: "error",
    };
  }
  if (trace.kind === "tool_plan" && Array.isArray(trace.tools) && trace.tools.length) {
    return {
      label: t("activity.planningNext"),
      kind: trace.kind,
      round: trace.round,
      state: "info",
    };
  }
  return null;
};

export const readTraceSlideIndex = (trace: ChatStreamTrace) => {
  if (typeof trace.slideIndex === "number" && trace.slideIndex >= 0) {
    return trace.slideIndex;
  }
  if (typeof trace.slideNumber === "number" && trace.slideNumber > 0) {
    return trace.slideNumber - 1;
  }
  return null;
};
