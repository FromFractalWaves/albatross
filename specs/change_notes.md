click on albatross in the top to go to home page

probably want to add live data pipeline status updates to the live data ui

total packets needs to be scrubbed

The :5590 scoping is smart. The spec's job is to get packets into the DB and push a notification. The API-side subscriber that receives that push and feeds preprocessing is a separate piece of work — probably a live_capture_pipeline spec that builds a new BasePipelineManager subclass for real data, wiring up the ZMQ subscriber where the mock pipeline has its in-process capture stage. That's a natural next spec after this one lands.