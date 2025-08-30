# Google Calendar and ICS  

## 📌 Overview  
This project integrates **Google Calendar** events and **ICS files** with **Google Tasks**.  
It allows you to automatically create tasks from calendar events, while also filtering them with keywords.  

---

## ⚙️ Setup  

1. **Enable Google APIs**  
   - Go to [Google Cloud Console](https://console.cloud.google.com/).  
   - Create a project and enable the **Google Calendar API** and **Google Tasks API**.  
   - Configure **OAuth 2.0 credentials** (desktop app).  
   - Download the `credentials.json` file and place it in the project’s root directory.  

2. **Install dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

3. **First Run**  
   - On the first execution, a browser will open to authenticate your Google account.  
   - A `token.json` file will be created and reused for future logins.  

---

## 🔑 Configuration  

The project uses two keyword arrays to control event → task conversion:  

- **`TASK_KEYWORDS`**  
  - Add words that, if present in the event’s title/summary, will create a Google Task.  
  - Example:  
    ```python
    TASK_KEYWORDS = ["exam", "meeting", "assignment"]
    ```

- **`IGNORE_KEYWORDS`**  
  - Add words that, if present in the event’s title/summary, will be ignored completely.  
  - Example:  
    ```python
    IGNORE_KEYWORDS = ["holiday", "birthday"]
    ```

⚠️ **Priority rule:**  
If an event matches both `TASK_KEYWORDS` and `IGNORE_KEYWORDS`, it will be **ignored**.  

---

## 📂 Usage  

Run the main script:  

```bash
python cal.py
```

You can also run with an `.ics` file:  

```bash
python cal.py my_calendar.ics
```

---

## ✅ Features  

- Reads events from **Google Calendar** and/or **ICS file**.  
- Creates tasks in **Google Tasks** based on your keyword rules.  
- Skips tasks containing ignore keywords.  
- Can clear all tasks in a specific task list before syncing (optional).  

---

## 📌 Notes  

- Make sure your system time and timezone are correct to avoid syncing issues.  
- If you want to use a **different Google Tasks list**, update the `TASKS_LIST_ID` in the code.
- You want to connect with moodle? Then access moodle and click on calendar, find export calendar and copy the URL, then add to URL ;-)
