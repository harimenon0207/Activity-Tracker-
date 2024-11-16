import dash
from dash import dcc, html, dash_table, Input, Output, State
import pandas as pd
import plotly.express as px
import datetime as dt
import base64
import io

# Initialize Dash app
app = dash.Dash(__name__)
app.title = 'Activity Tracker and Analyzer'

# Expected columns for validation
EXPECTED_COLUMNS = ['Type', 'Start', 'End', 'Duration', 'Start Condition', 'Start Location', 'End Condition', 'Notes']

# Function to check column names in uploaded data
def validate_csv_columns(df):
    if list(df.columns) != EXPECTED_COLUMNS:
        raise ValueError("CSV format does not match the expected columns")

# Function to convert 'Duration' into seconds
def convert_duration_to_minutes(df):
    # Ensure 'Duration' is a string and handle non-string entries gracefully
    df['Duration_minutes'] = df['Duration'].apply(lambda x: int(x.split(':')[0]) * 60 + int(x.split(':')[1]) if isinstance(x, str) and ':' in x else None)
    return df

# Function to check if 'Feed' and 'Diaper' types have intervals within 5 minutes
def check_close_time_intervals(df):
    feed_data = df[df['Type'] == 'Feed']
    diaper_data = df[df['Type'] == 'Diaper']
    
    # Merge to get pairs of Feed and Diaper events that are within 15 minutes of each other
    merged_data = pd.merge(feed_data, diaper_data, how='inner', suffixes=('_Feed', '_Diaper'), on='Start Location')
    merged_data['Close_interval'] = (
        (merged_data['Start_Feed'] - merged_data['End_Diaper']).abs().dt.total_seconds() <= 900
    )
    
    return merged_data[merged_data['Close_interval']]

# Layout for the Dash app
app.layout = html.Div([
    html.H1('Activity Tracker and Analyzer'),
    
    # File upload
    dcc.Upload(
        id='upload-data',
        children=html.Button('Upload CSV'),
        multiple=False
    ),
    html.Div(id='upload-alert', style={'color': 'red'}),
    
    # Dropdown for 'Type' values
    html.Label('Select Type:'),
    dcc.Dropdown(id='type-selector'),
    
    # Chart for events by day
    dcc.Graph(id='event-chart'),
    
    # Table for event counts
    dash_table.DataTable(id='event-table'),
    
    # Time range picker and average daily values for 'Feed'
    html.Label('Select Time Range:'),
    dcc.DatePickerRange(id='date-picker-range'),
    dash_table.DataTable(id='average-daily-table'),
    
    # Calendar heatmap for 'Type' with hour and day granularity
    html.Label('Select Type for Calendar Heatmap:'),
    dcc.Input(id='heatmap-type-input', placeholder='Enter Type', type='text'),
    dcc.Graph(id='calendar-heatmap')
])

# Global variable to store uploaded data
uploaded_data = None

# Callback to handle file upload and validate columns
@app.callback(
    Output('upload-alert', 'children'),
    Output('type-selector', 'options'),
    Output('date-picker-range', 'start_date'),
    Output('date-picker-range', 'end_date'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def handle_file_upload(contents, filename):
    global uploaded_data
    
    if contents:
        try:
            # Decode the content from base64
            content_type, content_string = contents.split(',')
            decoded_content = base64.b64decode(content_string)
            
            # Read the CSV into a DataFrame
            df = pd.read_csv(io.StringIO(decoded_content.decode('utf-8')))
            
            # Validate the format
            validate_csv_columns(df)
            
            # Convert 'Start' and 'End' columns to datetime
            df['Start'] = pd.to_datetime(df['Start'], errors='coerce')
            df['End'] = pd.to_datetime(df['End'], errors='coerce')
            
            # Convert 'Duration' to seconds
            uploaded_data = convert_duration_to_minutes(df)
            
            # Populate the 'Type' dropdown options
            type_options = [{'label': type, 'value': type} for type in uploaded_data['Type'].unique()]
            
            # Set default date range for date pickers
            start_date = uploaded_data['Start'].min().date()
            end_date = uploaded_data['Start'].max().date()
            
            return f"File '{filename}' uploaded successfully!", type_options, start_date, end_date
        except Exception as e:
            return f"Error: {str(e)}", [], None, None
    return '', [], None, None


# Callback to update chart and table based on 'Type' selection
@app.callback(
    [Output('event-chart', 'figure'),
     Output('event-table', 'data')],
    [Input('type-selector', 'value')]
)
def update_chart(type_value):
    if uploaded_data is None or type_value is None:
        return {}, []
    
    filtered_data = uploaded_data[uploaded_data['Type'] == type_value]
    event_counts = filtered_data.groupby(filtered_data['Start'].dt.date).size().reset_index(name='Event Count')
    fig = px.line(event_counts, x='Start', y='Event Count', title=f'Event Count Over Time for {type_value}')

    return fig, event_counts.to_dict('records')

# Callback to calculate average daily values for 'Feed'
@app.callback(
    Output('average-daily-table', 'data'),
    [Input('date-picker-range', 'start_date'),
     Input('date-picker-range', 'end_date')]
)
def update_average_table(start_date, end_date):
    if uploaded_data is None:
        return []
    
    filtered_data = uploaded_data[(uploaded_data['Start'].dt.date >= pd.to_datetime(start_date).date()) & 
                                  (uploaded_data['Start'].dt.date <= pd.to_datetime(end_date).date()) & 
                                  (uploaded_data['Type'] == 'Feed')]
    avg_duration = filtered_data['Duration_minutes'].mean()
    avg_events = filtered_data.groupby(filtered_data['Start'].dt.date).size().mean()

    result_df = pd.DataFrame({
        'Average Duration (Minutes)': [avg_duration],
        'Average Number of Events': [avg_events]
    })
    return result_df.to_dict('records')

# Callback to generate calendar heatmap based on type selection
@app.callback(
    Output('calendar-heatmap', 'figure'),
    [Input('heatmap-type-input', 'value')]
)
def update_calendar_heatmap(type_value):
    if uploaded_data is None or type_value is None:
        return {}

    # Filter data for selected type
    filtered_data = uploaded_data[uploaded_data['Type'] == type_value]
    
    # Extract day and hour from 'Start' timestamp
    filtered_data['Day'] = filtered_data['Start'].dt.date
    filtered_data['Hour'] = filtered_data['Start'].dt.hour
    
    # Generate a pivot table with counts by day and hour
    heatmap_data = filtered_data.pivot_table(index='Hour', columns='Day', aggfunc='size', fill_value=0)
    
    # Create heatmap figure
    fig = go.Figure(
        data=go.Heatmap(
            z=heatmap_data.values,
            x=heatmap_data.columns,
            y=heatmap_data.index,
            colorscale='Viridis',
            colorbar=dict(title="Number of Events"),
            hoverongaps=False
        )
    )
    
    # Set titles and labels for the heatmap
    fig.update_layout(
        title=f'Calendar Heatmap of Events by Hour and Day for {type_value}',
        xaxis_title='Date',
        yaxis_title='Hour of Day',
        yaxis=dict(dtick=1),
        xaxis=dict(
            tickformat="%Y-%m-%d",
            tickmode='array',
            tickvals=heatmap_data.columns
        )
    )

    return fig

if __name__ == '__main__':
    app.run_server(debug=True)
