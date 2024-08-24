#!/bin/bash

# Function to find and kill the processes
kill_processes() {
    # Find the processes matching the command
    pids=$(ps aux | grep "python agent.py start" | grep -v grep | awk '{print $2}')

    if [ -z "$pids" ]; then
        echo "No matching processes found."
    else
        echo "Found the following matching processes:"
        echo "$pids"

        # Prompt for confirmation before killing the processes
        read -p "Do you want to kill these processes? [y/N]: " confirm

        if [[ $confirm =~ ^[Yy]$ ]]; then
            # Kill the processes
            echo "Killing the processes..."
            kill $pids

            # Check if the processes were successfully killed
            for pid in $pids; do
                if ps -p $pid > /dev/null; then
                    echo "Process $pid is still running. Attempting force kill..."
                    kill -9 $pid
                fi
            done

            echo "Processes killed successfully."
        else
            ech "Aborted. No processes were killed."
        fi
    fi
}

# Call the function to find and kill the processes
kill_processes
