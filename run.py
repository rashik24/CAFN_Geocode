import io
import time

import pandas as pd
import requests
import streamlit as st


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Agency Geocoder",
    page_icon="📍",
    layout="wide",
)


# ============================================================
# CONFIG
# ============================================================
MAPBOX_URL = "https://api.mapbox.com/search/geocode/v6/forward"


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def read_uploaded_file(uploaded_file):
    extension = uploaded_file.name.lower().split(".")[-1]

    if extension == "csv":
        return pd.read_csv(uploaded_file)

    if extension in ["xlsx", "xls"]:
        return pd.read_excel(uploaded_file)

    raise ValueError("Please upload a CSV, XLSX, or XLS file.")


def clean_address(address):
    if pd.isna(address):
        return ""

    return " ".join(str(address).strip().split())


def geocode_address(address, mapbox_token, country="US"):
    address = clean_address(address)

    if not address:
        return {
            "Latitude": None,
            "Longitude": None,
            "Matched Address": None,
            "Geocode Status": "MISSING_ADDRESS",
            "Geocode Error": None,
        }

    params = {
        "q": address,
        "access_token": mapbox_token,
        "limit": 1,
        "autocomplete": "false",
    }

    if country.strip():
        params["country"] = country.strip().upper()

    try:
        response = requests.get(
            MAPBOX_URL,
            params=params,
            timeout=30,
        )

        data = response.json()

        if response.status_code != 200:
            return {
                "Latitude": None,
                "Longitude": None,
                "Matched Address": None,
                "Geocode Status": f"HTTP_{response.status_code}",
                "Geocode Error": data.get(
                    "message",
                    response.text,
                ),
            }

        features = data.get("features", [])

        if not features:
            return {
                "Latitude": None,
                "Longitude": None,
                "Matched Address": None,
                "Geocode Status": "ZERO_RESULTS",
                "Geocode Error": None,
            }

        first_result = features[0]

        geometry = first_result.get("geometry", {})
        coordinates = geometry.get("coordinates", [])

        if len(coordinates) < 2:
            return {
                "Latitude": None,
                "Longitude": None,
                "Matched Address": None,
                "Geocode Status": "INVALID_COORDINATES",
                "Geocode Error": "No valid coordinates were returned.",
            }

        # GeoJSON order is longitude, latitude
        longitude = coordinates[0]
        latitude = coordinates[1]

        properties = first_result.get("properties", {})

        matched_address = (
            properties.get("full_address")
            or properties.get("name")
            or first_result.get("place_name")
        )

        return {
            "Latitude": latitude,
            "Longitude": longitude,
            "Matched Address": matched_address,
            "Geocode Status": "OK",
            "Geocode Error": None,
        }

    except requests.exceptions.Timeout:
        return {
            "Latitude": None,
            "Longitude": None,
            "Matched Address": None,
            "Geocode Status": "TIMEOUT",
            "Geocode Error": "The Mapbox request timed out.",
        }

    except requests.exceptions.RequestException as error:
        return {
            "Latitude": None,
            "Longitude": None,
            "Matched Address": None,
            "Geocode Status": "REQUEST_FAILED",
            "Geocode Error": str(error),
        }

    except Exception as error:
        return {
            "Latitude": None,
            "Longitude": None,
            "Matched Address": None,
            "Geocode Status": "UNKNOWN_ERROR",
            "Geocode Error": str(error),
        }


def dataframe_to_excel(df):
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Geocoded Agencies",
        )

    output.seek(0)
    return output.getvalue()


# ============================================================
# APP HEADER
# ============================================================
st.title("📍 Agency Address Geocoder")

st.write(
    "Upload an Excel or CSV file containing agency addresses. "
    "The app will use Mapbox to generate latitude and longitude."
)


# ============================================================
# SIDEBAR SETTINGS
# ============================================================
with st.sidebar:
    st.header("Geocoding Settings")

    mapbox_token = "pk.eyJ1IjoicnNpZGRpcTIiLCJhIjoiY21jbjcwNWtkMHV5bzJpb2pnM3QxaDFtMyJ9.6T6i_QFuKQatpGaCFUvCKg"


    country = st.text_input(
        "Country code",
        value="US",
        help="Use US for United States addresses.",
    )

    request_delay = st.number_input(
        "Delay between requests",
        min_value=0.0,
        max_value=5.0,
        value=0.1,
        step=0.1,
        help="Pause between Mapbox requests.",
    )


# ============================================================
# FILE UPLOAD
# ============================================================
uploaded_file = st.file_uploader(
    "Upload agency file",
    type=["xlsx", "xls", "csv"],
)

if uploaded_file is None:
    st.info("Upload an Excel or CSV file to begin.")
    st.stop()


# ============================================================
# READ FILE
# ============================================================
try:
    df = read_uploaded_file(uploaded_file)

except Exception as error:
    st.error(f"Could not read the file: {error}")
    st.stop()


if df.empty:
    st.warning("The uploaded file contains no rows.")
    st.stop()


# ============================================================
# DATA PREVIEW
# ============================================================
st.subheader("Uploaded data")

st.write(f"Number of rows: **{len(df):,}**")

st.dataframe(
    df.head(25),
    use_container_width=True,
)


# ============================================================
# SELECT ADDRESS COLUMN
# ============================================================
default_address_index = 0

for index, column in enumerate(df.columns):
    if str(column).strip().lower() == "address":
        default_address_index = index
        break


address_column = st.selectbox(
    "Select the address column",
    options=list(df.columns),
    index=default_address_index,
)


skip_existing = st.checkbox(
    "Skip rows that already have Latitude and Longitude",
    value=True,
)


# ============================================================
# GEOCODE BUTTON
# ============================================================
run_geocoding = st.button(
    "Geocode agencies",
    type="primary",
    use_container_width=True,
)


# ============================================================
# RUN GEOCODING
# ============================================================
if run_geocoding:
    if not mapbox_token.strip():
        st.error("Enter your Mapbox access token.")
        st.stop()

    result_df = df.copy()

    output_columns = [
        "Latitude",
        "Longitude",
        "Matched Address",
        "Geocode Status",
        "Geocode Error",
    ]

    for column in output_columns:
        if column not in result_df.columns:
            result_df[column] = None

    progress_bar = st.progress(0)
    status_message = st.empty()

    total_rows = len(result_df)

    for row_number, (row_index, row) in enumerate(
        result_df.iterrows(),
        start=1,
    ):
        address = clean_address(row[address_column])

        existing_latitude = pd.to_numeric(
            pd.Series([row.get("Latitude")]),
            errors="coerce",
        ).iloc[0]

        existing_longitude = pd.to_numeric(
            pd.Series([row.get("Longitude")]),
            errors="coerce",
        ).iloc[0]

        has_existing_coordinates = (
            pd.notna(existing_latitude)
            and pd.notna(existing_longitude)
        )

        if skip_existing and has_existing_coordinates:
            result_df.at[
                row_index,
                "Geocode Status",
            ] = "EXISTING_COORDINATES"

        else:
            status_message.write(
                f"Geocoding {row_number:,} of "
                f"{total_rows:,}: {address}"
            )

            geocode_result = geocode_address(
                address=address,
                mapbox_token=mapbox_token.strip(),
                country=country,
            )

            for column, value in geocode_result.items():
                result_df.at[row_index, column] = value

            if request_delay > 0 and row_number < total_rows:
                time.sleep(request_delay)

        progress_bar.progress(row_number / total_rows)

    progress_bar.empty()
    status_message.empty()

    result_df["Latitude"] = pd.to_numeric(
        result_df["Latitude"],
        errors="coerce",
    )

    result_df["Longitude"] = pd.to_numeric(
        result_df["Longitude"],
        errors="coerce",
    )

    st.session_state["geocoded_results"] = result_df


# ============================================================
# DISPLAY RESULTS
# ============================================================
if "geocoded_results" in st.session_state:
    result_df = st.session_state["geocoded_results"]

    valid_coordinates = (
        result_df["Latitude"].notna()
        & result_df["Longitude"].notna()
    )

    matched_count = int(valid_coordinates.sum())
    unmatched_count = int((~valid_coordinates).sum())

    st.subheader("Geocoding summary")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Total agencies",
        f"{len(result_df):,}",
    )

    col2.metric(
        "Successfully geocoded",
        f"{matched_count:,}",
    )

    col3.metric(
        "Not geocoded",
        f"{unmatched_count:,}",
    )


    # ========================================================
    # RESULTS TABLE
    # ========================================================
    st.subheader("Results")

    st.dataframe(
        result_df,
        use_container_width=True,
    )


    # ========================================================
    # MAP
    # ========================================================
    if matched_count > 0:
        st.subheader("Agency map")

        map_df = result_df.loc[
            valid_coordinates,
            ["Latitude", "Longitude"],
        ].copy()

        map_df = map_df.rename(
            columns={
                "Latitude": "latitude",
                "Longitude": "longitude",
            }
        )

        st.map(map_df)


    # ========================================================
    # UNMATCHED ROWS
    # ========================================================
    if unmatched_count > 0:
        st.subheader("Addresses requiring review")

        review_columns = [
            address_column,
            "Geocode Status",
            "Geocode Error",
        ]

        if "Matched Address" in result_df.columns:
            review_columns.append("Matched Address")

        st.dataframe(
            result_df.loc[
                ~valid_coordinates,
                review_columns,
            ],
            use_container_width=True,
        )


    # ========================================================
    # DOWNLOAD EXCEL
    # ========================================================
    excel_output = dataframe_to_excel(result_df)

    st.download_button(
        label="Download geocoded Excel file",
        data=excel_output,
        file_name="Geocoded_Agencies.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        type="primary",
        use_container_width=True,
    )
# app.py

import io
import math

import pandas as pd
import streamlit as st


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Approximate Drive-Time Matrix",
    page_icon="🚗",
    layout="wide",
)

st.title("🚗 Tract-to-Agency Approximate Drive-Time Matrix")

st.write(
    "Upload a geocoded agency file and a tract-coordinate file. "
    "The tool estimates road distance and travel time using "
    "geodesic distance, a road-distance multiplier, and an "
    "assumed average driving speed."
)


# ============================================================
# DEFAULT COLUMN NAMES
# ============================================================
DEFAULT_TRACT_ID_COL = "GEOID"
DEFAULT_TRACT_LAT_COL = "YCoord"
DEFAULT_TRACT_LNG_COL = "XCoord"

DEFAULT_AGENCY_ID_COL = "Agency No."
DEFAULT_AGENCY_NAME_COL = "Site Name"
DEFAULT_AGENCY_LAT_COL = "Latitude"
DEFAULT_AGENCY_LNG_COL = "Longitude"


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def read_uploaded_file(uploaded_file):
    extension = uploaded_file.name.lower().split(".")[-1]

    if extension == "csv":
        return pd.read_csv(
            uploaded_file,
            dtype=str,
        )

    if extension in {"xlsx", "xls"}:
        return pd.read_excel(
            uploaded_file,
            dtype=str,
        )

    raise ValueError("Upload a CSV, XLSX, or XLS file.")


def clean_geoid(series):
    """
    Keep GEOID as text and remove Excel-style trailing '.0'.
    """

    return (
        series
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(11)
    )


def clean_text(series):
    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
    )


def haversine_miles(lat1, lon1, lat2, lon2):
    """
    Calculate straight-line distance in miles between two
    latitude/longitude coordinates.
    """

    earth_radius_miles = 3958.7613

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    a = min(1.0, max(0.0, a))

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_miles * c


def seconds_to_text(seconds):
    if pd.isna(seconds):
        return None

    total_minutes = int(round(seconds / 60))

    if total_minutes < 60:
        return f"{total_minutes} mins"

    hours = total_minutes // 60
    minutes = total_minutes % 60

    if minutes == 0:
        return f"{hours} hr"

    return f"{hours} hr {minutes} mins"


def miles_to_text(miles):
    if pd.isna(miles):
        return None

    return f"{miles:.1f} mi"


def dataframe_to_csv_bytes(df):
    return df.to_csv(
        index=False,
    ).encode("utf-8-sig")


# ============================================================
# MATRIX FUNCTION
# ============================================================
def compute_approximate_drive_time_matrix(
    tracts_df,
    agencies_df,
    tract_id_col,
    tract_lat_col,
    tract_lng_col,
    agency_id_col,
    agency_name_col,
    agency_lat_col,
    agency_lng_col,
    road_factor,
    average_speed_mph,
    progress_bar=None,
    status_placeholder=None,
):
    """
    Calculate all tract-agency combinations.

    Travel-time approximation:

        estimated road distance
            = geodesic distance × road factor

        estimated travel time
            = estimated road distance ÷ average speed
    """

    if road_factor <= 0:
        raise ValueError(
            "Road factor must be greater than zero."
        )

    if average_speed_mph <= 0:
        raise ValueError(
            "Average speed must be greater than zero."
        )

    required_tract_columns = [
        tract_id_col,
        tract_lat_col,
        tract_lng_col,
    ]

    required_agency_columns = [
        agency_id_col,
        agency_name_col,
        agency_lat_col,
        agency_lng_col,
    ]

    missing_tract_columns = [
        column
        for column in required_tract_columns
        if column not in tracts_df.columns
    ]

    missing_agency_columns = [
        column
        for column in required_agency_columns
        if column not in agencies_df.columns
    ]

    if missing_tract_columns:
        raise ValueError(
            f"Missing tract columns: {missing_tract_columns}"
        )

    if missing_agency_columns:
        raise ValueError(
            f"Missing agency columns: {missing_agency_columns}"
        )

    tracts = tracts_df[
        required_tract_columns
    ].copy()

    agencies = agencies_df[
        required_agency_columns
    ].copy()

    tracts[tract_id_col] = clean_geoid(
        tracts[tract_id_col]
    )

    agencies[agency_id_col] = clean_text(
        agencies[agency_id_col]
    )

    agencies[agency_name_col] = clean_text(
        agencies[agency_name_col]
    )

    tracts[tract_lat_col] = pd.to_numeric(
        tracts[tract_lat_col],
        errors="coerce",
    )

    tracts[tract_lng_col] = pd.to_numeric(
        tracts[tract_lng_col],
        errors="coerce",
    )

    agencies[agency_lat_col] = pd.to_numeric(
        agencies[agency_lat_col],
        errors="coerce",
    )

    agencies[agency_lng_col] = pd.to_numeric(
        agencies[agency_lng_col],
        errors="coerce",
    )

    tracts = tracts.dropna(
        subset=[
            tract_id_col,
            tract_lat_col,
            tract_lng_col,
        ]
    )

    agencies = agencies.dropna(
        subset=[
            agency_id_col,
            agency_name_col,
            agency_lat_col,
            agency_lng_col,
        ]
    )

    agencies = agencies[
        agencies[agency_id_col] != ""
    ]

    agencies = agencies[
        agencies[agency_name_col] != ""
    ]

    # One row per agency.
    agencies = agencies.drop_duplicates(
        subset=[agency_id_col],
        keep="first",
    )

    total_tracts = len(tracts)
    total_pairs = total_tracts * len(agencies)

    if total_pairs == 0:
        raise ValueError(
            "No valid tract-agency pairs were available."
        )

    output_rows = []

    for tract_position, (_, tract) in enumerate(
        tracts.iterrows(),
        start=1,
    ):
        tract_id = tract[tract_id_col]
        tract_lat = float(tract[tract_lat_col])
        tract_lng = float(tract[tract_lng_col])

        if status_placeholder is not None:
            status_placeholder.write(
                f"Processing tract {tract_position:,} "
                f"of {total_tracts:,}: {tract_id}"
            )

        for _, agency in agencies.iterrows():
            agency_id = agency[agency_id_col]
            agency_name = agency[agency_name_col]
            agency_lat = float(agency[agency_lat_col])
            agency_lng = float(agency[agency_lng_col])

            geodesic_miles = haversine_miles(
                tract_lat,
                tract_lng,
                agency_lat,
                agency_lng,
            )

            estimated_road_miles = (
                geodesic_miles * road_factor
            )

            estimated_hours = (
                estimated_road_miles
                / average_speed_mph
            )

            drive_time_seconds = int(
                round(estimated_hours * 3600)
            )

            total_traveltime = (
                drive_time_seconds / 60
            )

            distance_meters = (
                estimated_road_miles * 1609.344
            )

            output_rows.append(
                {
                    "GEOID": tract_id,
                    "Agency No.": agency_id,
                    "Name": agency_name,
                    "drive_time_seconds": (
                        drive_time_seconds
                    ),
                    "total_traveltime": (
                        total_traveltime
                    ),
                    "distance_meters": (
                        distance_meters
                    ),
                    "total_miles": (
                        estimated_road_miles
                    ),
                    "geodesic_distance_miles": (
                        geodesic_miles
                    ),
                    "distance_text": miles_to_text(
                        estimated_road_miles
                    ),
                    "drive_time_text": seconds_to_text(
                        drive_time_seconds
                    ),
                    "road_factor": road_factor,
                    "average_speed_mph": (
                        average_speed_mph
                    ),
                    "status": "ESTIMATED",
                }
            )

        if progress_bar is not None:
            progress_bar.progress(
                tract_position / total_tracts
            )

    result_df = pd.DataFrame(output_rows)

    numeric_columns = [
        "geodesic_distance_miles",
        "total_miles",
        "distance_meters",
        "total_traveltime",
    ]

    result_df[numeric_columns] = (
        result_df[numeric_columns]
        .round(3)
    )

    return result_df


# ============================================================
# SIDEBAR SETTINGS
# ============================================================
with st.sidebar:
    st.header("Estimation settings")

    road_factor = st.number_input(
        "Road-distance factor",
        min_value=1.0,
        max_value=3.0,
        value=1.25,
        step=0.05,
        help=(
            "Estimated road distance equals straight-line "
            "distance multiplied by this factor."
        ),
    )

    average_speed_mph = st.number_input(
        "Average driving speed (mph)",
        min_value=5.0,
        max_value=80.0,
        value=30.0,
        step=1.0,
    )

    filter_wake_county = st.checkbox(
        "Keep only Wake County tracts",
        value=True,
        help=(
            "Wake County's North Carolina county FIPS "
            "code is 183."
        ),
    )


# ============================================================
# FILE UPLOADS
# ============================================================
col1, col2 = st.columns(2)

with col1:
    agency_file = st.file_uploader(
        "Upload geocoded agency file",
        type=["csv", "xlsx", "xls"],
        key="agency_file",
    )

with col2:
    tract_file = st.file_uploader(
        "Upload tract coordinate file",
        type=["csv", "xlsx", "xls"],
        key="tract_file",
    )


if agency_file is None or tract_file is None:
    st.info(
        "Upload both files to configure the columns and "
        "generate the matrix."
    )
    st.stop()


# ============================================================
# READ FILES
# ============================================================
try:
    agencies_df = read_uploaded_file(
        agency_file
    )

    raw_tracts_df = read_uploaded_file(
        tract_file
    )

except Exception as error:
    st.error(
        f"Could not read the uploaded files: {error}"
    )
    st.stop()


if agencies_df.empty:
    st.error(
        "The agency file contains no rows."
    )
    st.stop()

if raw_tracts_df.empty:
    st.error(
        "The tract file contains no rows."
    )
    st.stop()


# ============================================================
# COLUMN SELECTION
# ============================================================
st.subheader("1. Select agency columns")

agency_columns = agencies_df.columns.tolist()

agency_id_index = (
    agency_columns.index(DEFAULT_AGENCY_ID_COL)
    if DEFAULT_AGENCY_ID_COL in agency_columns
    else 0
)

agency_name_index = (
    agency_columns.index(DEFAULT_AGENCY_NAME_COL)
    if DEFAULT_AGENCY_NAME_COL in agency_columns
    else 0
)

agency_lat_index = (
    agency_columns.index(DEFAULT_AGENCY_LAT_COL)
    if DEFAULT_AGENCY_LAT_COL in agency_columns
    else 0
)

agency_lng_index = (
    agency_columns.index(DEFAULT_AGENCY_LNG_COL)
    if DEFAULT_AGENCY_LNG_COL in agency_columns
    else 0
)

a1, a2, a3, a4 = st.columns(4)

with a1:
    agency_id_col = st.selectbox(
        "Agency ID",
        agency_columns,
        index=agency_id_index,
    )

with a2:
    agency_name_col = st.selectbox(
        "Agency name",
        agency_columns,
        index=agency_name_index,
    )

with a3:
    agency_lat_col = st.selectbox(
        "Agency latitude",
        agency_columns,
        index=agency_lat_index,
    )

with a4:
    agency_lng_col = st.selectbox(
        "Agency longitude",
        agency_columns,
        index=agency_lng_index,
    )


st.subheader("2. Select tract columns")

tract_columns = raw_tracts_df.columns.tolist()

tract_id_index = (
    tract_columns.index(DEFAULT_TRACT_ID_COL)
    if DEFAULT_TRACT_ID_COL in tract_columns
    else 0
)

tract_lat_index = (
    tract_columns.index(DEFAULT_TRACT_LAT_COL)
    if DEFAULT_TRACT_LAT_COL in tract_columns
    else 0
)

tract_lng_index = (
    tract_columns.index(DEFAULT_TRACT_LNG_COL)
    if DEFAULT_TRACT_LNG_COL in tract_columns
    else 0
)

t1, t2, t3 = st.columns(3)

with t1:
    tract_id_source_col = st.selectbox(
        "Tract GEOID",
        tract_columns,
        index=tract_id_index,
    )

with t2:
    tract_lat_source_col = st.selectbox(
        "Tract latitude",
        tract_columns,
        index=tract_lat_index,
    )

with t3:
    tract_lng_source_col = st.selectbox(
        "Tract longitude",
        tract_columns,
        index=tract_lng_index,
    )


# ============================================================
# PREPARE TRACT DATA
# ============================================================
tracts_df = raw_tracts_df[
    [
        tract_id_source_col,
        tract_lat_source_col,
        tract_lng_source_col,
    ]
].copy()

tracts_df = tracts_df.rename(
    columns={
        tract_id_source_col: "GEOID",
        tract_lat_source_col: "TRACT_LAT_COL",
        tract_lng_source_col: "TRACT_LNG_COL",
    }
)

tracts_df["GEOID"] = clean_geoid(
    tracts_df["GEOID"]
)

tracts_df = tracts_df.drop_duplicates(
    subset=["GEOID"],
    keep="first",
)

# State FIPS = first two digits.
tracts_df["State_FIPS"] = (
    tracts_df["GEOID"].str[:2]
)

# County FIPS = digits 3 through 5.
tracts_df["County"] = (
    tracts_df["GEOID"].str[2:5]
)

if filter_wake_county:
    tracts_df = tracts_df[
        tracts_df["County"] == "183"
    ].copy()


# ============================================================
# PREVIEW
# ============================================================
st.subheader("3. Input summary")

summary1, summary2, summary3 = st.columns(3)

summary1.metric(
    "Agency rows",
    f"{len(agencies_df):,}",
)

summary2.metric(
    "Unique tract rows",
    f"{len(tracts_df):,}",
)

summary3.metric(
    "Expected pairs",
    f"{len(agencies_df) * len(tracts_df):,}",
)

with st.expander("Preview agency file"):
    st.dataframe(
        agencies_df.head(20),
        use_container_width=True,
    )

with st.expander("Preview prepared tract file"):
    st.dataframe(
        tracts_df.head(20),
        use_container_width=True,
    )


# ============================================================
# GENERATE MATRIX
# ============================================================
generate_button = st.button(
    "Generate approximate drive-time matrix",
    type="primary",
    use_container_width=True,
)


if generate_button:
    progress_bar = st.progress(0)
    status_placeholder = st.empty()

    try:
        drive_time_df = (
            compute_approximate_drive_time_matrix(
                tracts_df=tracts_df,
                agencies_df=agencies_df,
                tract_id_col="GEOID",
                tract_lat_col="TRACT_LAT_COL",
                tract_lng_col="TRACT_LNG_COL",
                agency_id_col=agency_id_col,
                agency_name_col=agency_name_col,
                agency_lat_col=agency_lat_col,
                agency_lng_col=agency_lng_col,
                road_factor=road_factor,
                average_speed_mph=average_speed_mph,
                progress_bar=progress_bar,
                status_placeholder=status_placeholder,
            )
        )

        progress_bar.empty()
        status_placeholder.empty()

        # Add agency information.
        agency_info = agencies_df.copy()

        agency_info[agency_id_col] = clean_text(
            agency_info[agency_id_col]
        )

        agency_info = agency_info.drop_duplicates(
            subset=[agency_id_col],
            keep="first",
        )

        # Avoid duplicate agency-name column during merge.
        agency_info = agency_info.drop(
            columns=[agency_name_col],
            errors="ignore",
        )

        drive_time_df = drive_time_df.merge(
            agency_info,
            left_on="Agency No.",
            right_on=agency_id_col,
            how="left",
            validate="many_to_one",
        )

        if (
            agency_id_col != "Agency No."
            and agency_id_col in drive_time_df.columns
        ):
            drive_time_df = drive_time_df.drop(
                columns=[agency_id_col]
            )

        # Add tract coordinates and county.
        tract_info = tracts_df[
            [
                "GEOID",
                "TRACT_LAT_COL",
                "TRACT_LNG_COL",
                "County",
            ]
        ].drop_duplicates(
            subset=["GEOID"],
            keep="first",
        )

        drive_time_df = drive_time_df.merge(
            tract_info,
            on="GEOID",
            how="left",
            validate="many_to_one",
        )

        # Put core fields first.
        preferred_columns = [
            "GEOID",
            "Agency No.",
            "Name",
            "drive_time_seconds",
            "total_traveltime",
            "distance_meters",
            "total_miles",
            "drive_time_text",
            "distance_text",
            "TRACT_LAT_COL",
            "TRACT_LNG_COL",
            "County",
        ]

        remaining_columns = [
            column
            for column in drive_time_df.columns
            if column not in preferred_columns
        ]

        final_columns = [
            column
            for column in preferred_columns
            if column in drive_time_df.columns
        ] + remaining_columns

        drive_time_df = drive_time_df[
            final_columns
        ]

        st.session_state[
            "drive_time_df"
        ] = drive_time_df

        st.success(
            f"Generated {len(drive_time_df):,} "
            "tract-agency records."
        )

    except Exception as error:
        progress_bar.empty()
        status_placeholder.empty()

        st.error(
            f"Matrix generation failed: {error}"
        )


# ============================================================
# RESULTS
# ============================================================
if "drive_time_df" in st.session_state:
    drive_time_df = st.session_state[
        "drive_time_df"
    ]

    st.subheader("4. Results")

    r1, r2, r3 = st.columns(3)

    r1.metric(
        "Matrix rows",
        f"{len(drive_time_df):,}",
    )

    r2.metric(
        "Unique GEOIDs",
        f"{drive_time_df['GEOID'].nunique():,}",
    )

    r3.metric(
        "Unique agencies",
        f"{drive_time_df['Agency No.'].nunique():,}",
    )

    st.dataframe(
        drive_time_df.head(500),
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = dataframe_to_csv_bytes(
        drive_time_df
    )

    st.download_button(
        label="Download ODM_CAFN_Summer_2.csv",
        data=csv_bytes,
        file_name="ODM_CAFN_Summer_2.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )
