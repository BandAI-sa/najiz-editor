export function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (character) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character] || character;
  });
}

function renderInlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>");
}

function flushParagraph(blocks, paragraphLines) {
  if (!paragraphLines.length) {
    return;
  }

  blocks.push(`<p>${paragraphLines.map((line) => renderInlineMarkdown(line)).join("<br />")}</p>`);
  paragraphLines.length = 0;
}

function flushList(blocks, listType, listItems) {
  if (!listType || !listItems.length) {
    return;
  }

  blocks.push(`<${listType}>${listItems.join("")}</${listType}>`);
  listItems.length = 0;
}

export function renderMarkdownToHtml(markdown) {
  const lines = String(markdown || "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  const paragraphLines = [];
  const listItems = [];
  let listType = "";

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      flushParagraph(blocks, paragraphLines);
      flushList(blocks, listType, listItems);
      listType = "";
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph(blocks, paragraphLines);
      flushList(blocks, listType, listItems);
      listType = "";
      const level = headingMatch[1].length;
      blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    if (/^---+$/.test(line)) {
      flushParagraph(blocks, paragraphLines);
      flushList(blocks, listType, listItems);
      listType = "";
      blocks.push("<hr />");
      continue;
    }

    const unorderedMatch = line.match(/^[-*]\s+(.*)$/);
    if (unorderedMatch) {
      flushParagraph(blocks, paragraphLines);
      if (listType && listType !== "ul") {
        flushList(blocks, listType, listItems);
      }
      listType = "ul";
      listItems.push(`<li>${renderInlineMarkdown(unorderedMatch[1])}</li>`);
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph(blocks, paragraphLines);
      if (listType && listType !== "ol") {
        flushList(blocks, listType, listItems);
      }
      listType = "ol";
      listItems.push(`<li>${renderInlineMarkdown(orderedMatch[1])}</li>`);
      continue;
    }

    if (listType) {
      flushList(blocks, listType, listItems);
      listType = "";
    }

    paragraphLines.push(line);
  }

  flushParagraph(blocks, paragraphLines);
  flushList(blocks, listType, listItems);
  return blocks.join("");
}

export function setMarkdownContent(element, markdown, fallback = "") {
  element.innerHTML = renderMarkdownToHtml(markdown || fallback);
}
