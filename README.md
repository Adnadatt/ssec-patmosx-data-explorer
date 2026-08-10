## Setup
Before running the server, build the file indexes by running the following commands from the project root:
```bash
python pickle_l2bc.py 
python pickle_l3.py
```
Each script takes about a minute to run and produces a `.pickle` file
(`l2bc_files.pickle` and `l3_files.pickle` respectively) that the server
loads on startup.

## Running the server
Start the server on port 8001:

```bash
sanic server --dev -p 8001
```

## Accessing the server remotely (via tyr)

If the server is running on `tyr`, open a **separate terminal** and tunnel port 8001 to your local machine:

```bash
ssh -NL 8001:localhost:8001 tyr
```

Leave this terminal open while you are using the server.
Then you can access the server at 

```bash
http://localhost:8001
```

## Project Structure

- `patmosxDataExplorer.py` — Sanic app, API routes, receives the requests from the user
- `l3_utils.py` — L3 data reading, computation, and plotting
- `plot_utils.py` — L2BC plotting
- `index.html` — frontend
- `pickle_l2bc.py` / `pickle_l3.py` — build the file indexes
- `products_l2bc.py` — L2BC product definitions
