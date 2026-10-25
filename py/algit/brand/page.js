const NL = String.fromCharCode(10);
const filesEl = document.getElementById("files");
const commitsEl = document.getElementById("commits");
const subjectEl = document.getElementById("subject");
const metaEl = document.getElementById("meta");
const bodyEl = document.getElementById("body");
const crumbsEl = document.getElementById("crumbs");
const branchEl = document.getElementById("branch");
const mailboxEl = document.getElementById("mailbox");
const findEl = document.getElementById("find");
const factsEl = document.getElementById("facts");

let tree = [];
let filePaths = [];
let currentAnchor = null;

function sizeText(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return value + " B";
  if (value < 1048576) return (value / 1024).toFixed(1) + " KiB";
  return (value / 1048576).toFixed(2) + " MiB";
}

function fact(label, value, total) {
  const wrap = document.createElement("div");
  if (total) wrap.className = "total";
  const term = document.createElement("dt");
  term.textContent = label;
  const number = document.createElement("dd");
  number.textContent = value;
  wrap.append(term, number);
  factsEl.append(wrap);
}

function showAccount(overview) {
  factsEl.replaceChildren();
  const paid = overview.account || {};
  if (paid.microalgo == null) fact("ALGO", "not recorded", true);
  else fact("ALGO", Number(paid.algo).toFixed(6), true);
  fact("microALGO", paid.microalgo == null ? "0" : String(paid.microalgo));
  fact("Notes", paid.notes == null ? "0" : String(paid.notes));
  fact("Size", sizeText(overview.bytes));
  fact("Files", String((overview.files || []).length));
  fact("Commits", String((overview.commits || []).length));
  if (paid.firstRound != null) {
    const span = paid.firstRound === paid.lastRound
      ? String(paid.firstRound)
      : paid.firstRound + " to " + paid.lastRound;
    fact("Rounds", span + " (" + paid.rounds + ")");
  }
  if (paid.pinned) fact("Pinned", String(paid.pinned));
  if (paid.head) fact("Head", String(paid.head).slice(0, 12));
}

function mark(anchor) {
  for (const node of document.querySelectorAll(".rail a")) node.removeAttribute("aria-current");
  currentAnchor = anchor || null;
  if (currentAnchor) currentAnchor.setAttribute("aria-current", "page");
}

function setCrumbs(path) {
  crumbsEl.replaceChildren();
  if (!path) return;
  path.split("/").forEach((part, index) => {
    if (index) {
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = "/";
      crumbsEl.append(sep);
    }
    const bit = document.createElement("span");
    bit.textContent = part;
    crumbsEl.append(bit);
  });
}

function clearBody() {
  bodyEl.replaceChildren();
}

function lineClass(line) {
  const trimmed = line.trim();
  if (trimmed.startsWith("#") || trimmed.startsWith("//")) return "cm";
  const head = trimmed.split(" ")[0];
  if (["def", "class", "function", "import", "from", "const", "let", "return"].includes(head)) return "kw";
  return "";
}

function showLines(text) {
  clearBody();
  if (text.startsWith("Binary file,")) {
    const note = document.createElement("p");
    note.textContent = text;
    bodyEl.append(note);
    return;
  }
  const pre = document.createElement("pre");
  pre.className = "file";
  text.split(NL).forEach((line, index) => {
    const row = document.createElement("span");
    row.className = "row";
    const number = document.createElement("span");
    number.className = "ln";
    number.textContent = String(index + 1);
    const code = document.createElement("span");
    code.className = "code " + lineClass(line);
    code.textContent = line.length ? line : " ";
    row.append(number, code);
    pre.append(row, document.createTextNode(NL));
  });
  bodyEl.append(pre);
}

function showPatch(text) {
  clearBody();
  const pre = document.createElement("pre");
  pre.className = "diff";
  for (const line of text.split(NL)) {
    const span = document.createElement("span");
    span.textContent = line + NL;
    if (line.startsWith("@@") || line.startsWith("+++") || line.startsWith("---")) span.className = "hunk";
    else if (line.startsWith("+")) span.className = "add";
    else if (line.startsWith("-")) span.className = "del";
    pre.append(span);
  }
  bodyEl.append(pre);
}

function fileBytes(path) {
  const walk = (nodes) => {
    for (const node of nodes) {
      if (node.path === path) return node.bytes;
      if (node.children) {
        const found = walk(node.children);
        if (found != null) return found;
      }
    }
    return null;
  };
  return walk(tree);
}

async function showFile(path, anchor) {
  mark(anchor);
  setCrumbs(path);
  const response = await fetch("/api/file?path=" + encodeURIComponent(path));
  subjectEl.textContent = path.split("/").pop();
  const network = mailboxEl.dataset.network || "";
  const size = sizeText(fileBytes(path));
  metaEl.textContent = network ? network + " · " + size : size;
  showLines(await response.text());
  try {
    sessionStorage.setItem("algit-open", path);
  } catch (_) {
    /* storage can be off */
  }
}

async function showDiff(rev, path) {
  setCrumbs(path);
  const response = await fetch("/api/diff?rev=" + encodeURIComponent(rev) + "&path=" + encodeURIComponent(path));
  subjectEl.textContent = path.split("/").pop();
  showPatch(await response.text());
}

async function showCommit(commit, anchor) {
  mark(anchor);
  setCrumbs("");
  const response = await fetch("/api/commit?rev=" + encodeURIComponent(commit.id));
  if (!response.ok) {
    subjectEl.textContent = commit.subject;
    showLines(await response.text());
    return;
  }
  const data = await response.json();
  subjectEl.textContent = data.subject;
  let detail = data.author + ", " + new Date(data.at * 1000).toLocaleString();
  if (typeof commit.microalgo === "number") {
    detail += " · " + commit.notes + " notes · " + (commit.microalgo / 1000000).toFixed(6) + " ALGO";
  }
  metaEl.textContent = detail;
  clearBody();
  if (typeof commit.objects === "number" && typeof commit.notes === "number") {
    const introduced = document.createElement("p");
    introduced.textContent = "This commit introduced " + commit.objects + " objects in " + commit.notes + " notes.";
    bodyEl.append(introduced);
  }
  const list = document.createElement("ul");
  list.className = "changed";
  for (const file of data.files) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = "#";
    const badge = document.createElement("span");
    badge.className = "status";
    badge.textContent = file.status.slice(0, 1);
    link.append(badge, document.createTextNode("  " + file.path));
    const sized = fileBytes(file.path);
    if (sized != null) {
      const bytes = document.createElement("span");
      bytes.className = "bytes";
      bytes.textContent = "  " + sizeText(sized);
      link.append(bytes);
    }
    link.addEventListener("click", (event) => {
      event.preventDefault();
      showDiff(data.id, file.path);
    });
    item.append(link);
    list.append(item);
  }
  if (!data.files.length) {
    const empty = document.createElement("p");
    empty.textContent = "This commit does not change a file.";
    bodyEl.append(empty);
  }
  bodyEl.append(list);
}

function matches(node, needle) {
  if (!needle) return true;
  if (!node.children) return String(node.path || node.name).toLowerCase().includes(needle);
  return node.children.some((child) => matches(child, needle));
}

function renderTree(nodes, host, depth, needle) {
  const list = document.createElement("ul");
  list.className = "tree";
  for (const node of nodes) {
    if (node.children) {
      if (needle && !matches(node, needle)) continue;
      const item = document.createElement("li");
      const details = document.createElement("details");
      const hidden = node.name.startsWith(".") && depth === 0 && !needle;
      if ((depth === 0 && !hidden) || needle) details.open = true;
      const summary = document.createElement("summary");
      summary.textContent = node.name;
      details.append(summary);
      const nest = document.createElement("div");
      nest.className = "nest";
      renderTree(node.children, nest, depth + 1, needle);
      details.append(nest);
      item.append(details);
      list.append(item);
    } else if (!needle || String(node.path).toLowerCase().includes(needle)) {
      const item = document.createElement("li");
      item.className = "file";
      const link = document.createElement("a");
      link.href = "#";
      link.textContent = node.name;
      link.dataset.path = node.path;
      link.addEventListener("click", (event) => {
        event.preventDefault();
        showFile(node.path, link);
      });
      const size = document.createElement("span");
      size.className = "bytes";
      size.textContent = sizeText(node.bytes);
      item.append(link, size);
      list.append(item);
    }
  }
  if (list.childElementCount) host.append(list);
}

function drawTree(query) {
  filesEl.replaceChildren();
  renderTree(tree, filesEl, 0, query.trim().toLowerCase());
}

function anchorFor(path) {
  return filesEl.querySelector('a[data-path="' + CSS.escape(path) + '"]');
}

try {
  const overviewResponse = await fetch("/api/overview");
  if (!overviewResponse.ok) {
    subjectEl.textContent = "The repository did not load.";
    showLines(await overviewResponse.text());
    throw new Error("overview");
  }
  const overview = await overviewResponse.json();
  tree = overview.tree || [];
  filePaths = overview.files || [];
  showAccount(overview);
  branchEl.textContent = overview.branch || "";
  mailboxEl.textContent = overview.mailbox || "This page is on this machine.";
  mailboxEl.dataset.network = overview.network || "";
  document.title = (overview.branch || "ALGit") + " · ALGit";
  drawTree("");
  findEl.addEventListener("input", () => drawTree(findEl.value));
  for (const commit of overview.commits || []) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = "#";
    const hash = document.createElement("span");
    hash.className = "hash";
    hash.textContent = String(commit.id).slice(0, 7);
    link.append(hash, document.createTextNode("  " + commit.subject));
    if (typeof commit.microalgo === "number") {
      const cost = document.createElement("span");
      cost.className = "cost";
      cost.textContent = (commit.microalgo / 1000000).toFixed(6);
      link.append(cost);
    }
    link.addEventListener("click", (event) => {
      event.preventDefault();
      showCommit(commit, link);
    });
    item.append(link);
    commitsEl.append(item);
  }
  let remembered = "";
  try {
    remembered = sessionStorage.getItem("algit-open") || "";
  } catch (_) {
    remembered = "";
  }
  const initial = filePaths.includes(remembered)
    ? remembered
    : filePaths.includes("README.md")
      ? "README.md"
      : filePaths[0];
  if (initial) showFile(initial, anchorFor(initial));
} catch (error) {
  if (subjectEl.textContent !== "The repository did not load.") {
    subjectEl.textContent = "The page script failed.";
    metaEl.textContent = error && error.message ? error.message : String(error);
  }
}

document.addEventListener("keydown", (event) => {
  const typing = event.target && (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA");
  if (event.key === "/" && !typing) {
    event.preventDefault();
    findEl.focus();
  }
  if (event.key === "Escape" && event.target === findEl) {
    findEl.value = "";
    drawTree("");
    findEl.blur();
  }
});
