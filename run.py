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
# ============================================================
# APPROXIMATE TRACT-TO-AGENCY DRIVE-TIME MATRIX
# Uses:
#   1. Geocoded agencies from the previous Streamlit block
#   2. Fixed ODM FBCENC file for tract coordinates
# ============================================================

import math
import pandas as pd
import streamlit as st


# ============================================================
# CONFIG
# ============================================================
TRACT_COORDINATE_FILE = "ODM FBCENC 2.csv"

TRACT_ID_COL = "GEOID"
TRACT_LAT_COL = "TRACT_LAT_COL"
TRACT_LNG_COL = "TRACT_LNG_COL"

AGENCY_ID_COL = "Agency No."
AGENCY_NAME_COL = "Site Name"
AGENCY_LAT_COL = "Latitude"
AGENCY_LNG_COL = "Longitude"

ROAD_FACTOR_DEFAULT = 1.25
AVERAGE_SPEED_DEFAULT = 30.0


# ============================================================
# HELPERS
# ============================================================
def clean_geoid(series):
    """
    Keep GEOID as an 11-character string.
    Removes Excel-style trailing .0.
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
    Calculate straight-line distance in miles.
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


def compute_approximate_drive_time_matrix(
    tracts_df,
    agencies_df,
    road_factor,
    average_speed_mph,
    progress_bar=None,
    status_placeholder=None,
):
    """
    Create one row for every tract-agency pair.
    """

    required_tract_columns = [
        TRACT_ID_COL,
        TRACT_LAT_COL,
        TRACT_LNG_COL,
    ]

    required_agency_columns = [
        AGENCY_ID_COL,
        AGENCY_NAME_COL,
        AGENCY_LAT_COL,
        AGENCY_LNG_COL,
    ]

    missing_tract_columns = [
        col
        for col in required_tract_columns
        if col not in tracts_df.columns
    ]

    missing_agency_columns = [
        col
        for col in required_agency_columns
        if col not in agencies_df.columns
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

    tracts[TRACT_ID_COL] = clean_geoid(
        tracts[TRACT_ID_COL]
    )

    agencies[AGENCY_ID_COL] = clean_text(
        agencies[AGENCY_ID_COL]
    )

    agencies[AGENCY_NAME_COL] = clean_text(
        agencies[AGENCY_NAME_COL]
    )

    tracts[TRACT_LAT_COL] = pd.to_numeric(
        tracts[TRACT_LAT_COL],
        errors="coerce",
    )

    tracts[TRACT_LNG_COL] = pd.to_numeric(
        tracts[TRACT_LNG_COL],
        errors="coerce",
    )

    agencies[AGENCY_LAT_COL] = pd.to_numeric(
        agencies[AGENCY_LAT_COL],
        errors="coerce",
    )

    agencies[AGENCY_LNG_COL] = pd.to_numeric(
        agencies[AGENCY_LNG_COL],
        errors="coerce",
    )

    tracts = tracts.dropna(
        subset=[
            TRACT_ID_COL,
            TRACT_LAT_COL,
            TRACT_LNG_COL,
        ]
    )

    agencies = agencies.dropna(
        subset=[
            AGENCY_ID_COL,
            AGENCY_NAME_COL,
            AGENCY_LAT_COL,
            AGENCY_LNG_COL,
        ]
    )

    agencies = agencies[
        agencies[AGENCY_ID_COL] != ""
    ]

    agencies = agencies[
        agencies[AGENCY_NAME_COL] != ""
    ]

    # One coordinate record per tract
    tracts = tracts.drop_duplicates(
        subset=[TRACT_ID_COL],
        keep="first",
    )

    # One record per agency
    agencies = agencies.drop_duplicates(
        subset=[AGENCY_ID_COL],
        keep="first",
    )

    if tracts.empty:
        raise ValueError(
            "No valid tract coordinate records were found."
        )

    if agencies.empty:
        raise ValueError(
            "No valid geocoded agency records were found."
        )

    output_rows = []

    total_tracts = len(tracts)

    for tract_position, (_, tract) in enumerate(
        tracts.iterrows(),
        start=1,
    ):
        tract_id = tract[TRACT_ID_COL]
        tract_lat = float(tract[TRACT_LAT_COL])
        tract_lng = float(tract[TRACT_LNG_COL])

        if status_placeholder is not None:
            status_placeholder.write(
                f"Processing tract {tract_position:,} "
                f"of {total_tracts:,}: {tract_id}"
            )

        for _, agency in agencies.iterrows():
            agency_id = agency[AGENCY_ID_COL]
            agency_name = agency[AGENCY_NAME_COL]

            agency_lat = float(
                agency[AGENCY_LAT_COL]
            )

            agency_lng = float(
                agency[AGENCY_LNG_COL]
            )

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
                    "Agency Name": agency_name,
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
                    "drive_time_text": (
                        seconds_to_text(
                            drive_time_seconds
                        )
                    ),
                    "distance_text": (
                        miles_to_text(
                            estimated_road_miles
                        )
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

    result_df = pd.DataFrame(
        output_rows
    )

    numeric_columns = [
        "total_traveltime",
        "distance_meters",
        "total_miles",
        "geodesic_distance_miles",
    ]

    result_df[numeric_columns] = (
        result_df[numeric_columns]
        .round(3)
    )

    return result_df


# ============================================================
# SHOW MATRIX SECTION ONLY AFTER GEOCODING EXISTS
# ============================================================
if "geocoded_results" in st.session_state:

    st.divider()
    st.header(
        "🚗 Create Approximate Drive-Time Matrix"
    )

    # Agencies created in the previous geocoding block
    agencies_df = (
        st.session_state["geocoded_results"]
        .copy()
    )

    # --------------------------------------------------------
    # Read fixed tract coordinate file
    # --------------------------------------------------------
    try:
        raw_tract_df = pd.read_csv(
            TRACT_COORDINATE_FILE,
            dtype={"GEOID": str},
        )

    except FileNotFoundError:
        st.error(
            f"Could not find {TRACT_COORDINATE_FILE}. "
            "Place it in the same folder as app.py."
        )
        st.stop()

    except Exception as error:
        st.error(
            f"Could not read the tract file: {error}"
        )
        st.stop()

    required_raw_tract_columns = [
        "GEOID",
        "YCoord",
        "XCoord",
    ]

    missing_raw_columns = [
        col
        for col in required_raw_tract_columns
        if col not in raw_tract_df.columns
    ]

    if missing_raw_columns:
        st.error(
            "The tract file is missing columns: "
            f"{missing_raw_columns}"
        )
        st.stop()

    # --------------------------------------------------------
    # Prepare tract coordinates
    # --------------------------------------------------------
    tracts_df = raw_tract_df[
        [
            "GEOID",
            "YCoord",
            "XCoord",
        ]
    ].copy()

    tracts_df = tracts_df.rename(
        columns={
            "YCoord": "TRACT_LAT_COL",
            "XCoord": "TRACT_LNG_COL",
        }
    )

    tracts_df["GEOID"] = clean_geoid(
        tracts_df["GEOID"]
    )

    tracts_df = tracts_df.drop_duplicates(
        subset=["GEOID"],
        keep="first",
    )

    tracts_df["County"] = (
        tracts_df["GEOID"]
        .str[2:5]
    )

    # Wake County only
    tracts_df = tracts_df[
        tracts_df["County"] == "183"
    ].copy()

    # --------------------------------------------------------
    # Validate agency column names
    # --------------------------------------------------------
    required_agency_columns = [
        "Agency No.",
        "Site Name",
        "Latitude",
        "Longitude",
    ]

    missing_agency_columns = [
        col
        for col in required_agency_columns
        if col not in agencies_df.columns
    ]

    if missing_agency_columns:
        st.error(
            "The geocoded agency data is missing columns: "
            f"{missing_agency_columns}"
        )

        st.write(
            "Available columns:",
            agencies_df.columns.tolist(),
        )

        st.stop()

    # --------------------------------------------------------
    # Settings
    # --------------------------------------------------------
    setting_col1, setting_col2 = st.columns(2)

    with setting_col1:
        road_factor = st.number_input(
            "Road-distance factor",
            min_value=1.0,
            max_value=3.0,
            value=ROAD_FACTOR_DEFAULT,
            step=0.05,
            key="matrix_road_factor",
        )

    with setting_col2:
        average_speed_mph = st.number_input(
            "Average driving speed (mph)",
            min_value=5.0,
            max_value=80.0,
            value=AVERAGE_SPEED_DEFAULT,
            step=1.0,
            key="matrix_average_speed",
        )

    valid_agencies = agencies_df.dropna(
        subset=[
            "Agency No.",
            "Site Name",
            "Latitude",
            "Longitude",
        ]
    )

    summary_col1, summary_col2, summary_col3 = (
        st.columns(3)
    )

    summary_col1.metric(
        "Valid agencies",
        f"{len(valid_agencies):,}",
    )

    summary_col2.metric(
        "Wake County tracts",
        f"{len(tracts_df):,}",
    )

    summary_col3.metric(
        "Expected matrix rows",
        f"{len(valid_agencies) * len(tracts_df):,}",
    )

    with st.expander(
        "Preview geocoded agency data"
    ):
        st.dataframe(
            agencies_df.head(20),
            use_container_width=True,
        )

    with st.expander(
        "Preview tract coordinate data"
    ):
        st.dataframe(
            tracts_df.head(20),
            use_container_width=True,
        )

    # --------------------------------------------------------
    # Generate matrix
    # --------------------------------------------------------
    generate_matrix = st.button(
        "Generate drive-time matrix",
        type="primary",
        use_container_width=True,
        key="generate_matrix_button",
    )

    if generate_matrix:
        progress_bar = st.progress(0)
        status_placeholder = st.empty()

        try:
            drive_time_df = (
                compute_approximate_drive_time_matrix(
                    tracts_df=tracts_df,
                    agencies_df=agencies_df,
                    road_factor=road_factor,
                    average_speed_mph=(
                        average_speed_mph
                    ),
                    progress_bar=progress_bar,
                    status_placeholder=(
                        status_placeholder
                    ),
                )
            )

            # -----------------------------------------------
            # Merge all agency fields
            # -----------------------------------------------
            agency_info_df = agencies_df.copy()

            agency_info_df[
                "Agency No."
            ] = clean_text(
                agency_info_df["Agency No."]
            )

            agency_info_df = (
                agency_info_df
                .drop_duplicates(
                    subset=["Agency No."],
                    keep="first",
                )
            )

            # Name is already in matrix as Agency Name
            agency_info_df = (
                agency_info_df
                .drop(
                    columns=["Site Name"],
                    errors="ignore",
                )
            )

            drive_time_df = (
                drive_time_df.merge(
                    agency_info_df,
                    on="Agency No.",
                    how="left",
                    validate="many_to_one",
                )
            )

            # -----------------------------------------------
            # Merge tract coordinates and county
            # -----------------------------------------------
            tract_info_df = (
                tracts_df[
                    [
                        "GEOID",
                        "TRACT_LAT_COL",
                        "TRACT_LNG_COL",
                        "County",
                    ]
                ]
                .drop_duplicates(
                    subset=["GEOID"],
                    keep="first",
                )
            )

            drive_time_df = (
                drive_time_df.merge(
                    tract_info_df,
                    on="GEOID",
                    how="left",
                    validate="many_to_one",
                )
            )

            # -----------------------------------------------
            # Column order
            # -----------------------------------------------
            preferred_columns = [
                "GEOID",
                "Agency No.",
                "Agency Name",
                "drive_time_seconds",
                "total_traveltime",
                "distance_meters",
                "total_miles",
                "Latitude",
                "Longitude",
                "Address",
                "Operating Hours",
                "TRACT_LAT_COL",
                "TRACT_LNG_COL",
                "County",
                "drive_time_text",
                "distance_text",
                "geodesic_distance_miles",
                "road_factor",
                "average_speed_mph",
                "status",
            ]

            remaining_columns = [
                col
                for col in drive_time_df.columns
                if col not in preferred_columns
            ]

            final_columns = [
                col
                for col in preferred_columns
                if col in drive_time_df.columns
            ] + remaining_columns

            drive_time_df = (
                drive_time_df[final_columns]
            )

            st.session_state[
                "drive_time_df"
            ] = drive_time_df

            progress_bar.empty()
            status_placeholder.empty()

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
# MATRIX RESULTS AND DOWNLOAD
# ============================================================
if "drive_time_df" in st.session_state:

    drive_time_df = (
        st.session_state["drive_time_df"]
    )

    st.subheader("Drive-Time Matrix Results")

    result_col1, result_col2, result_col3 = (
        st.columns(3)
    )

    result_col1.metric(
        "Matrix rows",
        f"{len(drive_time_df):,}",
    )

    result_col2.metric(
        "Unique GEOIDs",
        f"{drive_time_df['GEOID'].nunique():,}",
    )

    result_col3.metric(
        "Unique agencies",
        f"{drive_time_df['Agency No.'].nunique():,}",
    )

    st.dataframe(
        drive_time_df.head(500),
        use_container_width=True,
        hide_index=True,
    )

    csv_output = (
        drive_time_df
        .to_csv(index=False)
        .encode("utf-8-sig")
    )

    st.download_button(
        label="Download ODM_CAFN_Summer_2.csv",
        data=csv_output,
        file_name="ODM_CAFN_Summer_2.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )
