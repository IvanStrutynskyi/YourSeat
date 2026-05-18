document.addEventListener("DOMContentLoaded", () => {
    const navToggle = document.querySelector(".nav-toggle");
    const navMenu = document.querySelector(".nav-menu");

    if (navToggle && navMenu) {
        navMenu.setAttribute("aria-hidden", "true");

        navToggle.addEventListener("click", () => {
            const isOpen = navMenu.classList.toggle("is-open");
            navToggle.setAttribute("aria-expanded", String(isOpen));
            navMenu.setAttribute("aria-hidden", String(!isOpen));
        });
    }

    document.querySelectorAll(".alert").forEach((alert) => {
        const closeButton = alert.querySelector(".alert__close");
        if (closeButton) {
            closeButton.addEventListener("click", () => alert.remove());
        }

        window.setTimeout(() => {
            if (alert.isConnected) {
                alert.remove();
            }
        }, 5000);
    });

    const noticeRoot = document.querySelector("[data-notice-root]");
    if (noticeRoot) {
        const noticeToggle = noticeRoot.querySelector("[data-notice-toggle]");
        const noticePanel = noticeRoot.querySelector("[data-notice-panel]");
        const noticeBadge = noticeRoot.querySelector("[data-notice-badge]");
        const noticeItems = Array.from(noticeRoot.querySelectorAll("[data-notice-item]"));
        const noticeUnreadText = noticeRoot.querySelector("[data-notice-unread-text]");
        const markReadUrl = noticeRoot.dataset.markReadUrl || "";
        let pendingMarkedIds = [];
        let pendingVisualReadSync = false;

        const syncNoticeState = () => {
            let unreadCount = 0;

            noticeItems.forEach((item) => {
                const isUnread = item.classList.contains("is-unread");
                if (isUnread) {
                    unreadCount += 1;
                }
            });

            if (noticeBadge) {
                noticeBadge.hidden = unreadCount === 0;
                noticeBadge.textContent = unreadCount;
            }

            if (noticeToggle) {
                noticeToggle.classList.toggle("has-badge", unreadCount > 0);
            }

            if (noticeUnreadText) {
                if (unreadCount > 0) {
                    noticeUnreadText.textContent = `${unreadCount} непрочитаних`;
                } else if (noticeItems.length > 0) {
                    noticeUnreadText.textContent = "Усі прочитано";
                } else {
                    noticeUnreadText.textContent = "Немає новин";
                }
            }
        };

        const applyMarkedReadState = () => {
            if (!pendingMarkedIds.length) {
                return;
            }

            const markedSet = new Set(pendingMarkedIds.map((value) => String(value)));
            noticeItems.forEach((item) => {
                const notificationId = String(item.dataset.notificationId || "");
                if (!markedSet.has(notificationId)) {
                    return;
                }

                item.classList.remove("is-unread");
                item.classList.add("is-read");
                const dot = item.querySelector(".nav-notice-item__dot");
                if (dot) {
                    dot.remove();
                }
            });

            pendingMarkedIds = [];
            pendingVisualReadSync = false;
            syncNoticeState();
        };

        const markNotificationsRead = async () => {
            const unreadItems = noticeItems.filter((item) => item.classList.contains("is-unread"));
            if (!markReadUrl || unreadItems.length === 0) {
                return;
            }

            try {
                const response = await window.fetch(markReadUrl, {
                    method: "POST",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });

                if (!response.ok) {
                    return;
                }

                const payload = await response.json();
                if (!payload.ok) {
                    return;
                }

                pendingMarkedIds = Array.isArray(payload.marked_ids) ? payload.marked_ids : [];
                pendingVisualReadSync = pendingMarkedIds.length > 0;

                if (noticeBadge) {
                    noticeBadge.hidden = true;
                    noticeBadge.textContent = "0";
                }
                if (noticeToggle) {
                    noticeToggle.classList.remove("has-badge");
                }
                if (noticeUnreadText) {
                    noticeUnreadText.textContent = noticeItems.length > 0 ? "Усі прочитано" : "Немає новин";
                }
            } catch (_error) {
            }
        };

        const closeNoticePanel = () => {
            if (!noticePanel || !noticeToggle) {
                return;
            }
            noticePanel.hidden = true;
            noticeToggle.setAttribute("aria-expanded", "false");
            if (pendingVisualReadSync) {
                applyMarkedReadState();
            }
        };

        if (noticeToggle && noticePanel) {
            noticeToggle.addEventListener("click", () => {
                const willOpen = noticePanel.hidden;
                noticePanel.hidden = !willOpen;
                noticeToggle.setAttribute("aria-expanded", String(willOpen));

                if (willOpen) {
                    void markNotificationsRead();
                } else if (pendingVisualReadSync) {
                    applyMarkedReadState();
                }
            });

            document.addEventListener("click", (event) => {
                if (!noticeRoot.contains(event.target)) {
                    closeNoticePanel();
                }
            });

            document.addEventListener("keydown", (event) => {
                if (event.key === "Escape") {
                    closeNoticePanel();
                }
            });
        }

        syncNoticeState();
    }

    const datetimeInputs = document.querySelectorAll('input[type="datetime-local"][data-min-now="true"]');
    if (datetimeInputs.length > 0) {
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        const minValue = now.toISOString().slice(0, 16);
        datetimeInputs.forEach((input) => {
            input.min = minValue;
        });
    }

    const dateInputs = document.querySelectorAll('input[type="date"][data-min-today="true"]');
    if (dateInputs.length > 0) {
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        const minDate = now.toISOString().slice(0, 10);
        dateInputs.forEach((input) => {
            input.min = minDate;
        });
    }

    document.querySelectorAll("[data-sync-target]").forEach((source) => {
        const targetId = source.getAttribute("data-sync-target");
        const target = document.getElementById(targetId);

        if (!target) {
            return;
        }

        const syncValue = () => {
            target.value = source.value;
            target.dispatchEvent(new Event("change", { bubbles: true }));
        };

        source.addEventListener("change", syncValue);
        source.addEventListener("input", syncValue);
    });

    const bookingHoursRoot = document.querySelector("[data-booking-hours]");
    const bookingDateInput = document.getElementById("booking_date");
    const bookingTimeInput = document.getElementById("booking_time");
    const bookingDurationInput = document.getElementById("booking_duration");
    const intervalTexts = document.querySelectorAll("[data-reservation-interval-text]");

    if (bookingHoursRoot && bookingDateInput && bookingTimeInput && bookingDurationInput && intervalTexts.length > 0) {
        const durationLabels = {
            90: "1.5 години",
            120: "2 години",
            150: "2.5 години",
            180: "3 години",
        };
        const pad = (value) => String(value).padStart(2, "0");
        const openingTime = bookingHoursRoot.dataset.openingTime || "00:00";
        const closingTime = bookingHoursRoot.dataset.closingTime || "23:59";
        const slotStepMinutes = 15;
        const invalidMessage = bookingHoursRoot.dataset.invalidMessage || "Неможливо створити бронювання на обраний час";
        const currentDateTimeValue = bookingHoursRoot.dataset.currentDatetime || "";
        const currentDateTime = currentDateTimeValue ? new Date(currentDateTimeValue) : new Date();

        const availabilityDateInput = bookingHoursRoot.querySelector('.form-grid--availability input[name="reservation_date"]');
        const availabilityTimeInput = bookingHoursRoot.querySelector('.form-grid--availability select[name="reservation_time"]');
        const availabilityDurationInput = bookingHoursRoot.querySelector('.form-grid--availability select[name="duration_minutes"]');
        const availabilitySubmitButton = bookingHoursRoot.querySelector('.form-grid--availability button[type="submit"]');
        const bookingSubmitButton = bookingHoursRoot.querySelector('.form-grid--booking-window button[type="submit"]');

        const bookingForms = [
            {
                dateInput: availabilityDateInput,
                timeInput: availabilityTimeInput,
                durationInput: availabilityDurationInput,
                submitButton: availabilitySubmitButton,
            },
            {
                dateInput: bookingDateInput,
                timeInput: bookingTimeInput,
                durationInput: bookingDurationInput,
                submitButton: bookingSubmitButton,
            },
        ].filter((item) => item.dateInput && item.timeInput && item.durationInput);

        const currentDateLabel = `${currentDateTime.getFullYear()}-${pad(currentDateTime.getMonth() + 1)}-${pad(currentDateTime.getDate())}`;

        const buildDateWithClock = (dateValue, clockValue) => {
            const [hours, minutes] = String(clockValue || "").split(":").map((item) => Number.parseInt(item, 10));
            const base = new Date(`${dateValue}T00:00:00`);
            if (Number.isNaN(base.getTime()) || Number.isNaN(hours) || Number.isNaN(minutes)) {
                return null;
            }
            base.setHours(hours, minutes, 0, 0);
            return base;
        };

        const roundUpToSlotStep = (date) => {
            const rounded = new Date(date.getTime());
            rounded.setSeconds(0, 0);
            const minutes = rounded.getMinutes();
            const remainder = minutes % slotStepMinutes;
            if (remainder !== 0) {
                rounded.setMinutes(minutes + (slotStepMinutes - remainder));
            }
            return rounded;
        };

        const formatTime = (date) => `${pad(date.getHours())}:${pad(date.getMinutes())}`;

        const getAllowedRange = (dateValue, durationValue) => {
            if (!dateValue || Number.isNaN(durationValue)) {
                return null;
            }

            const openingDate = buildDateWithClock(dateValue, openingTime);
            const closingDate = buildDateWithClock(dateValue, closingTime);
            if (!openingDate || !closingDate) {
                return null;
            }

            let minDate = openingDate;
            if (dateValue === currentDateLabel) {
                minDate = new Date(Math.max(openingDate.getTime(), roundUpToSlotStep(currentDateTime).getTime()));
            }

            const maxDate = new Date(closingDate.getTime() - durationValue * 60 * 1000);
            return { minDate, maxDate };
        };

        const buildTimeOptions = (range) => {
            if (!range || range.minDate > range.maxDate) {
                return [];
            }

            const options = [];
            const cursor = new Date(range.minDate.getTime());
            cursor.setSeconds(0, 0);

            while (cursor <= range.maxDate) {
                options.push(formatTime(cursor));
                cursor.setMinutes(cursor.getMinutes() + slotStepMinutes);
            }

            return options;
        };

        const renderTimeOptions = (timeInput, values, currentValue, emptyLabel = "Немає доступного часу") => {
            timeInput.innerHTML = "";

            if (values.length === 0) {
                const option = document.createElement("option");
                option.value = "";
                option.textContent = emptyLabel;
                timeInput.append(option);
                timeInput.value = "";
                return "";
            }

            values.forEach((value) => {
                const option = document.createElement("option");
                option.value = value;
                option.textContent = value;
                timeInput.append(option);
            });

            const nextValue = values.includes(currentValue) ? currentValue : values[0];
            timeInput.value = nextValue;
            return nextValue;
        };

        const validateTimeControl = ({ dateInput, timeInput, durationInput }, report = false) => {
            const durationValue = Number.parseInt(durationInput.value, 10);
            const dateValue = dateInput.value;
            const timeValue = timeInput.value;
            const range = getAllowedRange(dateValue, durationValue);
            const allowedOptions = buildTimeOptions(range);

            if (!dateValue || !timeValue || !range) {
                timeInput.setCustomValidity("");
                return true;
            }

            if (range.minDate > range.maxDate) {
                timeInput.setCustomValidity(invalidMessage);
                if (report) {
                    timeInput.reportValidity();
                }
                return false;
            }

            const selectedDate = buildDateWithClock(dateValue, timeValue);
            if (
                !selectedDate
                || selectedDate < range.minDate
                || selectedDate > range.maxDate
                || !allowedOptions.includes(timeValue)
            ) {
                timeInput.setCustomValidity(invalidMessage);
                if (report) {
                    timeInput.reportValidity();
                }
                return false;
            }

            timeInput.setCustomValidity("");
            return true;
        };

        const applyTimeBounds = ({ dateInput, timeInput, durationInput, submitButton }, clampExistingValue = true) => {
            const durationValue = Number.parseInt(durationInput.value, 10);
            const dateValue = dateInput.value;
            const range = getAllowedRange(dateValue, durationValue);
            const previousValue = timeInput.value;

            timeInput.disabled = false;
            if (submitButton) {
                submitButton.disabled = false;
            }

            if (!range) {
                renderTimeOptions(timeInput, [], "", "Оберіть дату");
                timeInput.disabled = true;
                if (submitButton) {
                    submitButton.disabled = true;
                }
                timeInput.setCustomValidity("");
                return;
            }

            if (range.minDate > range.maxDate) {
                renderTimeOptions(timeInput, [], "");
                timeInput.disabled = true;
                timeInput.setCustomValidity(invalidMessage);
                if (submitButton) {
                    submitButton.disabled = true;
                }
                if (previousValue !== timeInput.value) {
                    timeInput.dispatchEvent(new Event("change", { bubbles: true }));
                }
                return;
            }

            const allowedOptions = buildTimeOptions(range);
            const nextValue = renderTimeOptions(
                timeInput,
                allowedOptions,
                clampExistingValue ? previousValue : timeInput.value,
            );

            validateTimeControl({ dateInput, timeInput, durationInput }, false);
            if (previousValue !== nextValue) {
                timeInput.dispatchEvent(new Event("change", { bubbles: true }));
            }
        };

        const updateReservationInterval = () => {
            const dateValue = bookingDateInput.value;
            const timeValue = bookingTimeInput.value;
            const durationValue = Number.parseInt(bookingDurationInput.value, 10);

            let text = "Оберіть дату, час початку і тривалість бронювання";

            if (dateValue && timeValue && !Number.isNaN(durationValue)) {
                const start = new Date(`${dateValue}T${timeValue}`);

                if (!Number.isNaN(start.getTime())) {
                    const end = new Date(start.getTime() + durationValue * 60 * 1000);
                    const dateLabel = `${pad(start.getDate())}.${pad(start.getMonth() + 1)}.${start.getFullYear()}`;
                    const startLabel = `${pad(start.getHours())}:${pad(start.getMinutes())}`;
                    const endLabel = `${pad(end.getHours())}:${pad(end.getMinutes())}`;
                    const durationLabel = durationLabels[durationValue] || `${durationValue} хв`;

                    text = `Ваше бронювання триватиме з ${startLabel} до ${endLabel} ${dateLabel} • ${durationLabel}`;
                }
            }

            intervalTexts.forEach((node) => {
                node.textContent = text;
            });
        };

        bookingForms.forEach((controls) => {
            const { dateInput, timeInput, durationInput } = controls;

            const refreshBounds = () => applyTimeBounds(controls, true);
            dateInput.addEventListener("change", refreshBounds);
            durationInput.addEventListener("change", refreshBounds);
            timeInput.addEventListener("change", () => validateTimeControl(controls, false));
            timeInput.addEventListener("input", () => validateTimeControl(controls, false));

            const form = timeInput.closest("form");
            if (form) {
                form.addEventListener("submit", (event) => {
                    if (!validateTimeControl(controls, true)) {
                        event.preventDefault();
                    }
                });
            }

            applyTimeBounds(controls, false);
        });

        bookingDateInput.addEventListener("change", updateReservationInterval);
        bookingTimeInput.addEventListener("change", updateReservationInterval);
        bookingDurationInput.addEventListener("change", updateReservationInterval);
        updateReservationInterval();
    }

    const tableSelect = document.querySelector("[data-table-select]");
    const tableButtons = document.querySelectorAll("[data-table-option]");
    const selectedTableText = document.querySelector("[data-selected-table-text]");

    if (tableSelect && tableButtons.length > 0) {
        const updateSelectedTable = (tableId) => {
            tableButtons.forEach((button) => {
                button.classList.toggle("is-selected", button.dataset.tableId === tableId);
            });

            if (!selectedTableText) {
                return;
            }

            const activeButton = Array.from(tableButtons).find((button) => button.dataset.tableId === tableId);
            if (activeButton) {
                selectedTableText.textContent = `Столик ${activeButton.dataset.tableNumber} • ${activeButton.dataset.tableSeats} місць`;
            } else {
                selectedTableText.textContent = "Натисніть на столик на схемі залу";
            }
        };

        tableButtons.forEach((button) => {
            button.addEventListener("click", () => {
                if (button.disabled) {
                    return;
                }

                tableSelect.value = button.dataset.tableId;
                updateSelectedTable(button.dataset.tableId);
            });
        });

        tableSelect.addEventListener("change", () => {
            updateSelectedTable(tableSelect.value);
        });

        updateSelectedTable(tableSelect.value);
    }

    const tabButtons = document.querySelectorAll("[data-tab-target]");
    const tabPanels = document.querySelectorAll("[data-tab-panel]");

    if (tabButtons.length > 0 && tabPanels.length > 0) {
        const activateTab = (target, syncHash = true) => {
            tabButtons.forEach((button) => {
                button.classList.toggle("is-active", button.dataset.tabTarget === target);
            });

            tabPanels.forEach((panel) => {
                panel.classList.toggle("is-active", panel.dataset.tabPanel === target);
            });

            if (syncHash) {
                window.history.replaceState(null, "", `#${target}`);
            }
        };

        tabButtons.forEach((button) => {
            button.addEventListener("click", () => activateTab(button.dataset.tabTarget));
        });

        const hashTarget = window.location.hash.replace("#", "");
        if (hashTarget) {
            activateTab(hashTarget, false);
        }
    }

    const filterGroups = document.querySelectorAll("[data-filter-group]");
    filterGroups.forEach((group) => {
        const buttons = group.querySelectorAll("[data-filter]");
        const items = document.querySelectorAll("[data-filter-item]");

        buttons.forEach((button) => {
            button.addEventListener("click", () => {
                const filter = button.dataset.filter;

                buttons.forEach((item) => item.classList.remove("is-active"));
                button.classList.add("is-active");

                items.forEach((item) => {
                    const matches = filter === "all" || item.dataset.status === filter;
                    item.style.display = matches ? "" : "none";
                });
            });
        });
    });

    const confirmModal = document.querySelector("[data-confirm-modal]");
    const confirmAcceptButton = confirmModal?.querySelector("[data-confirm-accept]");
    const confirmCloseButtons = confirmModal ? Array.from(confirmModal.querySelectorAll("[data-confirm-close]")) : [];
    const cancelConfirmForms = Array.from(document.querySelectorAll("[data-cancel-confirm-form]"));
    let pendingCancelForm = null;

    if (confirmModal && confirmAcceptButton) {
        confirmModal.hidden = true;
        document.body.classList.remove("modal-open");

        const closeConfirmModal = () => {
            confirmModal.hidden = true;
            document.body.classList.remove("modal-open");
            pendingCancelForm = null;
        };

        const openConfirmModal = (form) => {
            pendingCancelForm = form;
            confirmModal.hidden = false;
            document.body.classList.add("modal-open");
            confirmAcceptButton.focus();
        };

        cancelConfirmForms.forEach((form) => {
            form.addEventListener("submit", (event) => {
                if (form.dataset.confirmSubmit === "true") {
                    delete form.dataset.confirmSubmit;
                    return;
                }

                event.preventDefault();
                openConfirmModal(form);
            });
        });

        confirmAcceptButton.addEventListener("click", () => {
            if (!pendingCancelForm) {
                closeConfirmModal();
                return;
            }

            pendingCancelForm.dataset.confirmSubmit = "true";
            pendingCancelForm.requestSubmit();
            closeConfirmModal();
        });

        confirmCloseButtons.forEach((button) => {
            button.addEventListener("click", closeConfirmModal);
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !confirmModal.hidden) {
                closeConfirmModal();
            }
        });
    }

    const loginLockForms = document.querySelectorAll("[data-login-lock-form]");
    loginLockForms.forEach((form) => {
        const submitButton = form.querySelector("[data-lock-submit]");
        const note = form.querySelector("[data-lock-note]");
        const timer = form.querySelector("[data-lock-timer]");
        let remainingSeconds = Number.parseInt(form.dataset.lockSeconds || "0", 10);

        const formatCountdown = (seconds) => {
            const safeSeconds = Math.max(0, Number.parseInt(seconds, 10) || 0);
            const minutes = Math.floor(safeSeconds / 60);
            const remainder = safeSeconds % 60;
            return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
        };

        const setLockedState = (locked) => {
            if (submitButton) {
                submitButton.disabled = locked;
            }
            if (note) {
                note.classList.toggle("is-hidden", !locked);
            }
        };

        const syncCountdown = () => {
            if (timer) {
                timer.textContent = formatCountdown(remainingSeconds);
            }

            if (remainingSeconds <= 0) {
                setLockedState(false);
                return;
            }

            setLockedState(true);
            const intervalId = window.setInterval(() => {
                remainingSeconds -= 1;
                if (timer) {
                    timer.textContent = formatCountdown(remainingSeconds);
                }

                if (remainingSeconds <= 0) {
                    window.clearInterval(intervalId);
                    setLockedState(false);
                }
            }, 1000);
        };

        form.addEventListener("submit", (event) => {
            if (remainingSeconds > 0) {
                event.preventDefault();
            }
        });

        syncCountdown();
    });
});
