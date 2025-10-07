# 🏀 NBA PLAYER PROPS ALGORITHM 🏀

## Getting Started

Follow these instructions to set up the project environment and run the application on your local machine.

### Prerequisites

Before you begin, ensure you have the following installed:

* **Python 3.x:** Required to run the scripts. You can download it from [python.org](https://www.python.org/).
* **pip:** Python's package installer (usually comes with Python).
* **Git:** Needed to clone the repository. Download from [git-scm.com](https://git-scm.com/).
* **PostgreSQL:** A relational database system used to store data.
    * Download and install PostgreSQL from the official website: [postgresql.org/download/](https://www.postgresql.org/download/).
    * **Important:** After installation, make sure the PostgreSQL server is running. The method varies by OS (e.g., using `services.msc` on Windows, `systemctl start postgresql` on Linux, or the Postgres app on macOS).
    * You will need database credentials (username, password) and a database name. You might need to create a dedicated user and database for this project using tools like `psql` or pgAdmin.

### Installation Steps

1.  **Clone the Repository:**
    Open your terminal or command prompt and run:
    ```bash
    git clone https://github.com/m4nr44j/nba-betting
    cd nba_betting
    ```
2.  **Create a Virtual Environment:**
    It's best practice to isolate project dependencies using a virtual environment.
    ```bash
    python -m venv venv
    ```

3.  **Activate the Virtual Environment:**
    * **Windows (Command Prompt/PowerShell):**
        ```bash
        .\venv\Scripts\activate
        ```
    * **Windows (Git Bash):**
        ```bash
        source venv/Scripts/activate
        ```
    * **macOS/Linux:**
        ```bash
        source venv/bin/activate
        ```
    You should see `(venv)` prefixed to your command prompt line when activated.

4.  **Install Dependencies:**
    Install all required Python packages listed in `requirements.txt`:
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure Environment Variables (.env file):**
    Create a file named `.env` in the root directory of your project. This file will hold your sensitive credentials and configuration settings.

    **Important:** Add `.env` to your `.gitignore` file to prevent accidentally committing secrets.

    Paste the following structure into your `.env` file and fill in your specific details:

    ```dotenv
    # Database credentials
    DB_HOST=localhost          # Hostname or IP address of your PostgreSQL server
    DB_PORT=5432              # Port PostgreSQL is running on (default is 5432)
    DB_USER=your_db_username  # Your PostgreSQL username
    DB_NAME=your_db_name      # The name of the database created for this project
    DB_PASS=your_db_password  # The password for the PostgreSQL user

    #Replace the fields here with the variables above
    SQL_ENGINE='postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

    # API Keys
    ODDS_KEY=your_the_odds_api_key # Get your API key from [https://the-odds-api.com/](https://the-odds-api.com/)

    ```

    * Replace `your_db_username`, `your_db_name`, `your_db_password` with your actual PostgreSQL details.
    * Adjust `DB_HOST` and `DB_PORT` if your setup differs from the default.
    * Get your API key from [The Odds API](https://the-odds-api.com/) and insert it (will need paid key to get backtesting odds beyond included dates).

## Database Initialization

After setting up the environment and configuration, you need to initialize the database. This step typically creates necessary tables and populates them with initial data.

Ensure your virtual environment is activated and run:
```bash
python utility/initialize_database.py
```

This script should connect to the database specified in your .env file and perform the required setup. Check for any output messages indicating success or errors.

## Running the Application
With the setup complete, you can now run the main script to find player prop opportunities.

### Timing:
Run the script once per day. It's necessary to run it >30 minutes before the first scheduled NBA game of that day. This will allow enough time to get odds and injury data to run the models. The script will process all games for that day and generate predictions immediately.

Execute the main script from your activated virtual environment:

```bash
python run.py
```

### Output
The script generates two main output files:

1. **`output.txt`** - Easy-to-read betting recommendations
2. **`csv/output.csv`** - Detailed CSV data with all predictions and odds

#### Example Output (output.txt)

```
MIN vs PHI: Donte DiVincenzo Over 15.5 P+A (102 FD)
NOP vs LAL: Kelly Olynyk Over 18.5 P+R+A (-130 FD)
                        ...
```

## Backtesting

The project includes a comprehensive backtesting module located in the `backtest/` directory. This allows you to test the algorithm's performance against historical data.

### Running Backtests

```bash
python -m backtest.backtest
```

### Backtest Requirements

- Historical odds data files in `backtest/historical/` directory (format: `MM_DD_props.json`)
- Historical data includes November 2024 through June 2025 NBA season
- Properly configured database connection (same as main application)
- All main project dependencies installed

### Backtest Output

The backtest will provide:
- Daily profit/loss analysis
- Win/loss record tracking  
- Running total across all tested days
- Individual bet performance metrics
- Results saved to `backtest/picks.json`
