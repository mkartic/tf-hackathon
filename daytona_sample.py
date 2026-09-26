from daytona import Daytona, DaytonaConfig

# Define the configuration
config = DaytonaConfig(api_key="dtn_c95d7ce450597fe0f92328978825a9e8dfe4ff3cde0a32710d2fe6d3ea917986")

# Initialize the Daytona client
daytona = Daytona(config)

# Create the Sandbox instance
sandbox = daytona.create()

# Run the code securely inside the Sandbox
response = sandbox.process.code_run('print("Hello World from code!")')
if response.exit_code != 0:
  print(f"Error: {response.exit_code} {response.result}")
else:
    print(response.result)
