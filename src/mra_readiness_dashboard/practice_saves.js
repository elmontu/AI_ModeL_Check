(function (root, factory) {
    "use strict";
    var api = factory(root);
    if (typeof module === "object" && module.exports) {
        module.exports = api;
    } else {
        root.PracticeSaves = api;
        if (root.document) {
            if (root.document.readyState === "loading") {
                root.document.addEventListener("DOMContentLoaded", function () { api.mount(root.document); }, {once: true});
            } else {
                api.mount(root.document);
            }
        }
    }
}(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
    "use strict";

    var STORAGE_KEY = "mra.demo-practice-saves.v1";
    var WRITE_LOCK_NAME = "mra.demo-practice-saves.v1.write";
    var UI_SCHEMA = "local-fictional-practice-saves-ui/1";
    var EXPORT_SCHEMA = "local-fictional-practice-saves/1";
    var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
    var FORBIDDEN_NAME = /[\u0000-\u001f\u007f-\u009f\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]/u;
    var GUARDS = Object.freeze({
        fictional_example: true,
        public_synthetic_only: true,
        authentic_source_records_included: false,
        real_agency_decisions: "pending",
        original_substantive_gaps_open: 12,
        original_substantive_gaps_closed: 0,
        authorization_effect: "none",
        benchmark_executed: false,
        graded: false,
        learning_progress_saved: false
    });
    var MESSAGES = Object.freeze({
        DOMAIN_INVALID: "The saved-demo page configuration is unavailable. No demo was saved.",
        STORAGE_UNAVAILABLE: "Browser storage is unavailable or full. No saved-demo change was made.",
        STORAGE_CORRUPT: "Existing saved-demo data could not be read. It has been left unchanged.",
        STORAGE_CHANGED: "Saved demos changed in another tab. Review the current list and try again.",
        LOCK_UNAVAILABLE: "This browser cannot coordinate saved-demo changes. Saving, importing and removal are unavailable; reading, export, reload and comparison remain available.",
        LIMIT_REACHED: "This browser can keep at most twenty demos. Export a backup before removing an item you no longer need.",
        INVALID_NAME: "Use a name of one to eighty characters without control or hidden direction characters.",
        INVALID_CONFIGURATION: "This is not a supported complete fictional practice configuration.",
        ENTRY_NOT_FOUND: "That saved demo is no longer available. Review the current list.",
        INVALID_IMPORT: "This is not a supported canonical demo export. Use the dedicated JSON format produced by Export saved demos.",
        IMPORT_TOO_LARGE: "The demo file exceeds the sixty-four KiB import limit.",
        ID_UNAVAILABLE: "A new local demo identifier could not be created. No saved-demo change was made."
    });

    class LibraryError extends Error {
        constructor(code) {
            super(MESSAGES[code] || MESSAGES.INVALID_IMPORT);
            this.name = "LibraryError";
            this.code = code;
        }
    }

    function fail(code) { throw new LibraryError(code); }
    function demand(condition, code) { if (!condition) { fail(code); } }

    function plain(value) {
        if (value === null || typeof value !== "object" || Array.isArray(value)) { return false; }
        var prototype = Object.getPrototypeOf(value);
        if (prototype !== Object.prototype && prototype !== null) { return false; }
        if (Object.getOwnPropertySymbols(value).length) { return false; }
        return Object.values(Object.getOwnPropertyDescriptors(value)).every(function (descriptor) {
            return Object.prototype.hasOwnProperty.call(descriptor, "value");
        });
    }

    function exact(value, keys, code) {
        demand(plain(value), code);
        var actual = Object.getOwnPropertyNames(value).sort();
        var wanted = keys.slice().sort();
        demand(actual.length === wanted.length && actual.every(function (key, index) {
            return key === wanted[index];
        }), code);
    }

    function utf8Length(text, code) {
        demand(typeof text === "string", code);
        var bytes = 0;
        for (var character of text) {
            var point = character.codePointAt(0);
            demand(point < 0xd800 || point > 0xdfff, code);
            bytes += point <= 0x7f ? 1 : point <= 0x7ff ? 2 : point <= 0xffff ? 3 : 4;
        }
        return bytes;
    }

    function canonicalStringify(value) {
        function ordered(item) {
            if (item === null || typeof item === "boolean") { return item; }
            if (typeof item === "string") { utf8Length(item, "INVALID_IMPORT"); return item; }
            if (typeof item === "number") { demand(Number.isFinite(item), "INVALID_IMPORT"); return item; }
            if (Array.isArray(item)) { return item.map(ordered); }
            demand(plain(item), "INVALID_IMPORT");
            var result = Object.create(null);
            Object.keys(item).sort().forEach(function (key) {
                utf8Length(key, "INVALID_IMPORT");
                result[key] = ordered(item[key]);
            });
            return result;
        }
        return JSON.stringify(ordered(value));
    }

    function copy(value) { return JSON.parse(canonicalStringify(value)); }

    function normalizedName(value, maximum) {
        demand(typeof value === "string", "INVALID_NAME");
        utf8Length(value, "INVALID_NAME");
        demand(!FORBIDDEN_NAME.test(value), "INVALID_NAME");
        var trimmed = value.trim();
        demand(Array.from(trimmed).length > 0 && Array.from(trimmed).length <= maximum, "INVALID_NAME");
        return trimmed;
    }

    function createLibrary(domain, storage) {
        exact(domain, ["schema", "storage_key", "export_schema", "max_entries", "max_name_length",
            "max_file_bytes", "exercises", "controls", "candidate", "candidate_title"], "DOMAIN_INVALID");
        demand(domain.schema === UI_SCHEMA && domain.storage_key === STORAGE_KEY
            && domain.export_schema === EXPORT_SCHEMA, "DOMAIN_INVALID");
        demand(domain.max_entries === 20 && domain.max_name_length === 80
            && domain.max_file_bytes === 65536, "DOMAIN_INVALID");
        demand(Array.isArray(domain.exercises) && domain.exercises.length === 6
            && Array.isArray(domain.controls) && domain.controls.length === 12, "DOMAIN_INVALID");
        demand(domain.candidate === null ? domain.candidate_title === null
            : typeof domain.candidate_title === "string", "DOMAIN_INVALID");
        var exercises = Object.create(null);
        var controls = Object.create(null);
        var controlKeys = [];
        domain.exercises.forEach(function (row) {
            exact(row, ["id", "title"], "DOMAIN_INVALID");
            demand(typeof row.id === "string" && /^[a-z][a-z0-9-]*$/.test(row.id)
                && typeof row.title === "string" && !Object.prototype.hasOwnProperty.call(exercises, row.id), "DOMAIN_INVALID");
            utf8Length(row.title, "DOMAIN_INVALID");
            exercises[row.id] = row.title;
        });
        domain.controls.forEach(function (row) {
            exact(row, ["key", "label", "values"], "DOMAIN_INVALID");
            demand(typeof row.key === "string" && /^[a-z][a-z0-9_]*$/.test(row.key)
                && typeof row.label === "string" && !Object.prototype.hasOwnProperty.call(controls, row.key), "DOMAIN_INVALID");
            demand(Array.isArray(row.values) && row.values.length > 0, "DOMAIN_INVALID");
            demand(row.values.every(function (value) {
                return typeof value === "string" && /^[a-z][a-z0-9-]*$/.test(value);
            }) && new Set(row.values).size === row.values.length, "DOMAIN_INVALID");
            utf8Length(row.label, "DOMAIN_INVALID");
            controls[row.key] = new Set(row.values);
            controlKeys.push(row.key);
        });

        function configuration(value, code) {
            exact(value, ["exercise", "assumptions"], code);
            demand(typeof value.exercise === "string"
                && Object.prototype.hasOwnProperty.call(exercises, value.exercise), code);
            exact(value.assumptions, controlKeys, code);
            controlKeys.forEach(function (key) {
                demand(typeof value.assumptions[key] === "string" && controls[key].has(value.assumptions[key]), code);
            });
            return copy(value);
        }

        var candidate = null;
        if (domain.candidate !== null) {
            candidate = configuration(domain.candidate, "DOMAIN_INVALID");
            demand(domain.candidate_title === exercises[candidate.exercise], "DOMAIN_INVALID");
        }
        try {
            demand(storage && typeof storage.getItem === "function"
                && typeof storage.setItem === "function", "STORAGE_UNAVAILABLE");
        } catch (error) { fail("STORAGE_UNAVAILABLE"); }

        var maximumEntries = 20;
        var maximumNameLength = 80;
        var maximumFileBytes = 65536;

        function envelope(entries) {
            return Object.assign({schema: EXPORT_SCHEMA}, GUARDS, {entries: entries});
        }

        function validateEnvelope(value, code) {
            exact(value, ["schema", "entries"].concat(Object.keys(GUARDS)), code);
            demand(value.schema === EXPORT_SCHEMA, code);
            Object.keys(GUARDS).forEach(function (key) { demand(value[key] === GUARDS[key], code); });
            demand(Array.isArray(value.entries) && value.entries.length <= maximumEntries, code);
            var ids = new Set();
            value.entries.forEach(function (entry) {
                exact(entry, ["id", "name", "exercise", "assumptions"], code);
                demand(typeof entry.id === "string" && UUID.test(entry.id) && !ids.has(entry.id), code);
                ids.add(entry.id);
                try {
                    demand(entry.name === normalizedName(entry.name, maximumNameLength), code);
                } catch (error) { fail(code); }
                configuration({exercise: entry.exercise, assumptions: entry.assumptions}, code);
            });
            return value;
        }

        function parseEnvelope(text, code) {
            demand(typeof text === "string", code);
            var length;
            try { length = utf8Length(text, code); } catch (error) { fail(code); }
            if (length > maximumFileBytes) { fail(code === "INVALID_IMPORT" ? "IMPORT_TOO_LARGE" : code); }
            var value;
            try { value = JSON.parse(text); } catch (error) { fail(code); }
            validateEnvelope(value, code);
            demand(canonicalStringify(value) + "\n" === text, code);
            return value;
        }

        function rawRead() {
            var raw;
            try { raw = storage.getItem(STORAGE_KEY); } catch (error) { fail("STORAGE_UNAVAILABLE"); }
            demand(raw === null || typeof raw === "string", "STORAGE_UNAVAILABLE");
            return raw;
        }

        function state() {
            var raw = rawRead();
            return {raw: raw, entries: raw === null ? [] : parseEnvelope(raw, "STORAGE_CORRUPT").entries};
        }

        function commit(before, entries) {
            var outgoing = envelope(entries);
            validateEnvelope(outgoing, "INVALID_CONFIGURATION");
            var text = canonicalStringify(outgoing) + "\n";
            demand(utf8Length(text, "INVALID_CONFIGURATION") <= maximumFileBytes, "LIMIT_REACHED");
            demand(rawRead() === before.raw, "STORAGE_CHANGED");
            try { storage.setItem(STORAGE_KEY, text); } catch (error) { fail("STORAGE_UNAVAILABLE"); }
        }

        function newId(ids) {
            for (var attempt = 0; attempt < 16; attempt += 1) {
                var value;
                try {
                    demand(root.crypto && typeof root.crypto.randomUUID === "function", "ID_UNAVAILABLE");
                    value = root.crypto.randomUUID();
                } catch (error) { fail("ID_UNAVAILABLE"); }
                demand(typeof value === "string" && UUID.test(value), "ID_UNAVAILABLE");
                if (!ids.has(value)) { ids.add(value); return value; }
            }
            fail("ID_UNAVAILABLE");
        }

        function find(entries, id) {
            demand(typeof id === "string" && UUID.test(id), "ENTRY_NOT_FOUND");
            var entry = entries.find(function (row) { return row.id === id; });
            demand(entry !== undefined, "ENTRY_NOT_FOUND");
            return entry;
        }

        return Object.freeze({
            read: function () { return copy(state().entries); },
            save: function (name, selected) {
                var before = state();
                demand(before.entries.length < maximumEntries, "LIMIT_REACHED");
                var label = normalizedName(name, maximumNameLength);
                var choices = configuration(selected === undefined ? candidate : selected, "INVALID_CONFIGURATION");
                var ids = new Set(before.entries.map(function (entry) { return entry.id; }));
                var entry = {id: newId(ids), name: label, exercise: choices.exercise, assumptions: choices.assumptions};
                commit(before, before.entries.concat([entry]));
                return copy(entry);
            },
            remove: function (id) {
                var before = state();
                var entry = find(before.entries, id);
                commit(before, before.entries.filter(function (row) { return row.id !== id; }));
                return copy(entry);
            },
            importText: function (text) {
                var before = state();
                var incoming = parseEnvelope(text, "INVALID_IMPORT").entries;
                demand(before.entries.length + incoming.length <= maximumEntries, "LIMIT_REACHED");
                if (!incoming.length) { return []; }
                var ids = new Set(before.entries.map(function (entry) { return entry.id; }));
                var added = incoming.map(function (entry) {
                    return {id: newId(ids), name: entry.name, exercise: entry.exercise, assumptions: copy(entry.assumptions)};
                });
                commit(before, before.entries.concat(added));
                return copy(added);
            },
            exportText: function () {
                return canonicalStringify(envelope(state().entries)) + "\n";
            },
            practiceUrl: function (id) {
                var entry = find(state().entries, id);
                var pairs = [["exercise", entry.exercise]];
                controlKeys.forEach(function (key) { pairs.push([key, entry.assumptions[key]]); });
                return "/tutorial-practice?" + new URLSearchParams(pairs).toString() + "#practice-feedback";
            },
            compareUrl: function (leftId, rightId) {
                var entries = state().entries;
                var left = find(entries, leftId);
                var right = find(entries, rightId);
                var pairs = [["left_preset", "worked-example"], ["right_preset", "worked-example"]];
                [["left", left], ["right", right]].forEach(function (side) {
                    controlKeys.forEach(function (key) { pairs.push([side[0] + "_" + key, side[1].assumptions[key]]); });
                });
                return "/tutorial-compare?" + new URLSearchParams(pairs).toString() + "#comparison-results";
            }
        });
    }

    async function withWriteLock(navigatorLike, action) {
        demand(navigatorLike && navigatorLike.locks
            && typeof navigatorLike.locks.request === "function"
            && typeof action === "function", "LOCK_UNAVAILABLE");
        try {
            return await navigatorLike.locks.request(WRITE_LOCK_NAME, {mode: "exclusive"}, action);
        } catch (error) {
            if (error instanceof LibraryError) { throw error; }
            fail("LOCK_UNAVAILABLE");
        }
    }

    var mounted = new WeakMap();

    function mount(document) {
        var section = document.getElementById("practice-saves");
        if (!section) { return null; }
        if (mounted.has(section)) { return mounted.get(section); }
        var controller = {library: null, refresh: function () {}};
        mounted.set(section, controller);
        var notice = document.getElementById("saves-notice");
        var saveForm = document.getElementById("saves-save-form");
        var nameInput = document.getElementById("saves-name");
        var saveButton = document.getElementById("saves-save");
        var exportButton = document.getElementById("saves-export-all");
        var importInput = document.getElementById("saves-import-file");
        var importButton = document.getElementById("saves-import");
        var list = document.getElementById("saves-list");
        var left = document.getElementById("saves-left");
        var right = document.getElementById("saves-right");
        var compareButton = document.getElementById("saves-compare");
        var domain = null;
        var library = null;
        var entries = [];
        var readable = false;
        var busy = false;
        var fileReadPending = false;
        var pendingRemoval = null;

        function message(text, error) {
            if (notice) {
                notice.textContent = text;
                notice.setAttribute("data-kind", error ? "error" : "status");
            }
        }

        function report(error) {
            message(error instanceof LibraryError ? error.message : MESSAGES.STORAGE_UNAVAILABLE, true);
        }

        function coordinated() {
            try {
                return !!(root.navigator && root.navigator.locks
                    && typeof root.navigator.locks.request === "function");
            } catch (error) { return false; }
        }

        function updateButtons() {
            var mayChange = readable && coordinated() && !busy && !fileReadPending;
            if (saveButton) { saveButton.disabled = !mayChange || !domain || domain.candidate === null || entries.length >= 20; }
            if (exportButton) { exportButton.disabled = !readable || !entries.length; }
            if (importButton) {
                importButton.disabled = !mayChange || entries.length >= 20
                    || !importInput || !importInput.files || importInput.files.length !== 1;
            }
            if (left) { left.disabled = !readable || !entries.length; }
            if (right) { right.disabled = !readable || !entries.length; }
            if (compareButton) { compareButton.disabled = !readable || entries.length < 2; }
            if (list) {
                list.querySelectorAll('button[data-mutation="true"]').forEach(function (button) {
                    button.disabled = !mayChange;
                });
            }
        }

        function element(tag, text) {
            var node = document.createElement(tag);
            if (text !== undefined) { node.textContent = text; }
            return node;
        }

        function render() {
            try {
                entries = library.read();
                readable = true;
                var oldLeft = left.value;
                var oldRight = right.value;
                list.replaceChildren();
                left.replaceChildren();
                right.replaceChildren();
                if (!entries.length) {
                    list.appendChild(element("p", "No saved demos in this browser yet."));
                }
                entries.forEach(function (entry, index) {
                    var title = domain.exercises.find(function (exercise) { return exercise.id === entry.exercise; }).title;
                    var article = element("article");
                    article.setAttribute("role", "listitem");
                    article.setAttribute("data-demo-id", entry.id);
                    article.appendChild(element("h3", entry.name));
                    article.appendChild(element("p", title + " · Saved item " + (index + 1)));
                    var load = element("a", "Load practice");
                    load.setAttribute("href", library.practiceUrl(entry.id));
                    article.appendChild(load);
                    var remove = element("button", pendingRemoval === entry.id ? "Confirm removal" : "Remove demo");
                    remove.type = "button";
                    remove.setAttribute("data-mutation", "true");
                    remove.addEventListener("click", function () {
                        if (pendingRemoval !== entry.id) {
                            pendingRemoval = entry.id;
                            render();
                            message("Select Confirm removal to remove only this browser's saved copy of " + entry.name
                                + ". Exported files and other copies remain where you kept them.", false);
                            return;
                        }
                        mutate(function () {
                            demand(pendingRemoval === entry.id, "ENTRY_NOT_FOUND");
                            library.remove(entry.id);
                            pendingRemoval = null;
                            render();
                            message("Removed this browser's saved copy. Exported files and other copies were not changed.", false);
                        });
                    });
                    article.appendChild(remove);
                    if (pendingRemoval === entry.id) {
                        var cancel = element("button", "Cancel removal");
                        cancel.type = "button";
                        cancel.addEventListener("click", function () {
                            pendingRemoval = null;
                            render();
                            message("Removal cancelled. Saved demos were not changed.", false);
                        });
                        article.appendChild(cancel);
                    }
                    list.appendChild(article);
                    [left, right].forEach(function (select) {
                        var option = element("option", entry.name + " · " + title + " · Saved item " + (index + 1));
                        option.value = entry.id;
                        select.appendChild(option);
                    });
                });
                var ids = new Set(entries.map(function (entry) { return entry.id; }));
                if (entries.length) {
                    left.value = ids.has(oldLeft) ? oldLeft : entries[0].id;
                    right.value = ids.has(oldRight) && oldRight !== left.value ? oldRight
                        : (entries[1] || entries[0]).id;
                }
                updateButtons();
                return true;
            } catch (error) {
                readable = false;
                updateButtons();
                report(error);
                return false;
            }
        }

        async function mutate(action) {
            if (busy) { return; }
            busy = true;
            updateButtons();
            try {
                await withWriteLock(root.navigator, action);
            } catch (error) {
                report(error);
            } finally {
                busy = false;
                updateButtons();
            }
        }

        if (saveForm) {
            saveForm.addEventListener("submit", function (event) {
                event.preventDefault();
                if (!library || !domain || domain.candidate === null) { report(new LibraryError("INVALID_CONFIGURATION")); return; }
                var selectedName = nameInput.value;
                var selectedCandidate = copy(domain.candidate);
                mutate(function () {
                    var entry = library.save(selectedName, selectedCandidate);
                    pendingRemoval = null;
                    if (nameInput.value === selectedName) { nameInput.value = ""; }
                    render();
                    message("Saved locally: " + entry.name + ". This creates a separate fictional demo, with no agency or evidence effect.", false);
                });
            });
        }

        try {
            demand(notice && exportButton && importInput && importButton && list && left && right && compareButton, "DOMAIN_INVALID");
            domain = JSON.parse(section.getAttribute("data-library"));
            var browserStorage;
            try { browserStorage = root.localStorage; } catch (error) { fail("STORAGE_UNAVAILABLE"); }
            library = createLibrary(domain, browserStorage);
            controller.library = library;
            controller.refresh = render;
        } catch (error) {
            report(error instanceof LibraryError ? error : new LibraryError("DOMAIN_INVALID"));
            return controller;
        }

        importInput.addEventListener("change", updateButtons);
        exportButton.addEventListener("click", function () {
            try {
                var text = library.exportText();
                var blob = new root.Blob([text], {type: "application/json;charset=utf-8"});
                var url = root.URL.createObjectURL(blob);
                var link = element("a");
                link.href = url;
                link.download = "fictional-practice-demos.json";
                document.body.appendChild(link);
                link.click();
                link.remove();
                root.setTimeout(function () { root.URL.revokeObjectURL(url); }, 1000);
                message("Export requested. Keep the downloaded JSON in its exported format so it can be imported as new copies.", false);
            } catch (error) { report(error); }
        });

        importButton.addEventListener("click", async function () {
            if (busy || fileReadPending) { return; }
            fileReadPending = true;
            updateButtons();
            var file = importInput.files && importInput.files[0];
            try {
                demand(file && importInput.files.length === 1, "INVALID_IMPORT");
                demand(file.size <= 65536, "IMPORT_TOO_LARGE");
                var buffer = await file.arrayBuffer();
                demand(buffer.byteLength <= 65536, "IMPORT_TOO_LARGE");
                var text;
                try {
                    text = new root.TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(buffer);
                } catch (error) { fail("INVALID_IMPORT"); }
                await mutate(function () {
                    var added = library.importText(text);
                    pendingRemoval = null;
                    if (importInput.files && importInput.files[0] === file) { importInput.value = ""; }
                    render();
                    message("Imported " + added.length + " demos as new copies. Existing demos were not replaced; names may repeat.", false);
                });
            } catch (error) { report(error); }
            finally { fileReadPending = false; updateButtons(); }
        });

        compareButton.addEventListener("click", function () {
            try {
                root.location.assign(library.compareUrl(left.value, right.value));
            } catch (error) { report(error); }
        });

        if (typeof root.addEventListener === "function") {
            root.addEventListener("storage", function (event) {
                if (event.key === STORAGE_KEY || event.key === null) {
                    pendingRemoval = null;
                    if (render()) { message("Saved demos refreshed from this browser's current storage.", false); }
                }
            });
        }
        if (render()) {
            if (!coordinated()) { message(MESSAGES.LOCK_UNAVAILABLE, true); }
            else { message(entries.length ? entries.length + " saved demos in this browser." : "No saved demos in this browser yet.", false); }
        }
        return controller;
    }

    return Object.freeze({
        createLibrary: createLibrary,
        canonicalStringify: canonicalStringify,
        LibraryError: LibraryError,
        withWriteLock: withWriteLock,
        WRITE_LOCK_NAME: WRITE_LOCK_NAME,
        mount: mount
    });
}));
