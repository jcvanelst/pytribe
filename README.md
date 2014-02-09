pytribe
=======

Simple python API wrapper for communicating with the EyeTribe eye-tracking server

See example.py for an example of how to read tracking data using non-blocking threads and a queue.

To simply read a single set of data, first `import pytribe` then `data = pytribe.query_tracker()`
