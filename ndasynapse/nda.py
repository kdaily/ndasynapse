"""Functions to interact with NIMH Data Archive API.

"""

import io
import os
import json
import logging
import sys

import requests
import pandas
import boto3
from deprecated import deprecated

pandas.options.display.max_rows = None
pandas.options.display.max_columns = None
pandas.options.display.max_colwidth = 1000

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ch = logging.StreamHandler()
# ch.setLevel(logging.DEBUG)
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# ch.setFormatter(formatter)
# logger.addHandler(ch)

METADATA_COLUMNS = ['src_subject_id', 'experiment_id', 'subjectkey', 'sample_id_original',
                    'sample_id_biorepository', 'subject_sample_id_original', 'biorepository',
                    'subject_biorepository', 'sample_description', 'species', 'site', 'sex',
                    'sample_amount', 'phenotype',
                    'comments_misc', 'sample_unit', 'fileFormat']

SAMPLE_COLUMNS = ['collection_id', 'datasetid', 'experiment_id', 'sample_id_original', 'storage_protocol',
                  'sample_id_biorepository', 'organism', 'sample_amount', 'sample_unit',
                  'biorepository', 'comments_misc', 'site', 'genomics_sample03_id',
                  'src_subject_id', 'subjectkey']

SUBJECT_COLUMNS = ['src_subject_id', 'subjectkey', 'sex', 'race', 'phenotype',
                   'subject_sample_id_original', 'sample_description', 'subject_biorepository',
                   'sex']

EXPERIMENT_COLUMNS_CHANGE = {'additionalinformation.analysisSoftware.software': 'analysisSoftwareName',
                             'additionalinformation.equipment.equipmentName': 'equipmentName',
                             'experimentparameters.molecule.moleculeName': 'moleculeName',
                             'experimentparameters.platform.platformName': 'platformName',
                             'experimentparameters.platform.platformSubType': 'platformSubType',
                             'experimentparameters.platform.vendorName': 'vendorName',
                             'experimentparameters.technology.applicationName': 'applicationName',
                             'experimentparameters.technology.applicationSubType': 'applicationSubType',
                             'extraction.extractionProtocols.protocolName': 'extractionProtocolName',
                             'extraction.extractionKits.extractionKit': 'extractionKit',
                             'processing.processingKits.processingKit': 'processingKit'}

EQUIPMENT_NAME_REPLACEMENTS = {'Illumina HiSeq 2500,Illumina NextSeq 500': 'HiSeq2500,NextSeq500',
                               'Illumina NextSeq 500,Illumina HiSeq 2500': 'HiSeq2500,NextSeq500',
                               'Illumina HiSeq 4000,Illumina MiSeq': 'HiSeq4000,MiSeq',
                               'Illumina MiSeq,Illumina HiSeq 4000': 'HiSeq4000,MiSeq',
                               'Illumina NextSeq 500': 'NextSeq500',
                               'Illumina HiSeq 2500': 'HiSeq2500',
                               'Illumina HiSeq X Ten': 'HiSeqX',
                               'Illumina HiSeq 4000': 'HiSeq4000',
                               'Illumina MiSeq': 'MiSeq',
                               'BioNano IrysView': 'BionanoIrys'}

APPLICATION_SUBTYPE_REPLACEMENTS = {"Whole genome sequencing": "wholeGenomeSeq",
                                    "Exome sequencing": "exomeSeq",
                                    "Optical genome imaging": "wholeGenomeOpticalImaging"}

MANIFEST_COLUMNS = ['filename', 'md5', 'size']

def authenticate(config):
    """Authenticate to NDA.

    Args:
        config: A dict with 'username' and 'password' keys for NDA login.
    Returns:
        A requests.auth.HTTPBasicAuth object.

    """
    try:
        ndaconfig = config['nda']
    except KeyError:
        raise KeyError("Cannot find NDA credentials in config file.")

    auth = requests.auth.HTTPBasicAuth(ndaconfig['username'], ndaconfig['password'])
    
    return auth


def get_guid(auth, subjectkey: str) -> dict:
    """Get available data from the GUID API.

    Args:
        auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
        subjectkey: An NDA GUID (Globally Unique Identifier)
    Returns:
        dict from JSON format.
    """

    r = requests.get(f"https://nda.nih.gov/api/guid/{subjectkey}/",
                     auth=auth, headers={'Accept': 'application/json'})

    logger.debug(f"Request {r} for GUID {subjectkey}")

    if r.ok:
        return r.json()
    else:
        logger.debug(f"{r.status_code} - {r.url} - {r.text}")
        return None


def get_guid_data(auth, subjectkey: str, short_name: str) -> dict:
    """Get data from the GUID API.

    Args:
        auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
        subjectkey: An NDA GUID (Globally Unique Identifier)
        short_name: The data structure to return data for (e.g., genomics_sample03)
    Returns:
        dict from JSON format.
    """

    r = requests.get(f"https://nda.nih.gov/api/guid/{subjectkey}/data?short_name={short_name}",
                     auth=auth, headers={'Accept': 'application/json'})

    logger.debug(f"Request {r} for GUID {subjectkey}")

    if r.ok:
        return r.json()
    else:
        logger.debug(f"{r.status_code} - {r.url} - {r.text}")
        return None


def get_samples(auth, guid: str) -> dict:
    """Use the NDA api to get the `genomics_sample03` records for a GUID.
    
    Args:
        auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
        guid: An NDA GUID (Globally Unique Identifier)
    Returns:
        dict from JSON format.
    """

    return get_guid_data(auth=auth, subjectkey=guid, short_name="genomics_sample03")


def get_subjects(auth, guid):
    """Use the NDA API to get the `genomics_subject02` records for a GUID.
    
        Args:
            auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
            guid: An NDA GUID (also called the subjectkey).
        Returns:
            Data in JSON format.
    """

    return get_guid_data(auth=auth, subjectkey=guid, short_name="genomics_subject02")

def get_tissues(auth, guid):
    """Use the NDA GUID API to get the `ncihd_btb02` records for a GUID.

    These records are the brain and tissue bank information.

    Args:
        auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
        guid: An NDA GUID (also called the subjectkey).
    Returns:
        Data in JSON format.
    
    """

    return get_guid_data(auth=auth, subjectkey=guid, short_name="nichd_btb02")


def get_submission(auth, submissionid: int) -> dict:
    """Use the NDA Submission API to get a submission.

    Args:
        auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
        guid: An NDA submission ID.
    Returns:
        dict from JSON format.
    """

    r = requests.get(f"https://nda.nih.gov/api/submission/{submissionid}",
                     auth=auth, headers={'Accept': 'application/json'})

    logger.debug("Request %s for submission %s" % (r, submissionid))

    if r.ok:
        return r.json()
    else:
        logger.debug(f"{r.status_code} - {r.url} - {r.text}")
        return None


def get_submissions(auth, collectionid, status="Upload Completed", users_own_submissions=False):
    """Use the NDA Submission API to get submissions from a NDA collection.
    
    This is a separate service to get submission in batch that are related to a collection or a user.
    See `get_submission` to get a single submission by submission ID.

    Args:
        auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
        collectionid: An NDA collection ID or a list of NDA collection IDs. If None, gets all submissions.
        status: Status of submissions to retrieve. If None, gets all submissions.
        users_own_submissions: Return only user's own submissions. If False, must pass collection ID(s).
    Returns:
        dict from JSON format.
        
    """

    if isinstance(collectionid, (list,)):
        collectionid = ",".join(collectionid)

    r = requests.get("https://nda.nih.gov/api/submission/",
                     params={'usersOwnSubmissions': users_own_submissions,
                             'collectionId': collectionid,
                             'status': status},
                     auth=auth, headers={'Accept': 'application/json'})

    logger.debug("Request %s for collection %s" % (r.url, collectionid))

    if r.ok:
        return r.json()
    else:
        logger.debug(f"{r.status_code} - {r.url} - {r.text}")
        return None


def get_submission_files(auth, submissionid:int, submission_file_status:str="Complete", 
                         retrieve_files_to_upload:bool=False) -> dict:
    """Use the NDA Submission API to get files for an NDA submission.
    Args:
        auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
        submissionid: An NDA collection ID or a list of NDA collection IDs. If None, gets all submissions.
        submission_file_status: Status of submission files to retrieve, If None, gets all files.
        retrieve_files_to_upload: Flag indicating that only files that need to be uploaded be retrived.
    Returns:
        dict from JSON format.

    """

    r = requests.get(f"https://nda.nih.gov/api/submission/{submissionid}/files",
                     params={'submissionFileStatus': submission_file_status,
                             'retrieveFilesToUpload': retrieve_files_to_upload},
                     auth=auth, headers={'Accept': 'application/json'})

    logger.debug(f"Request {r.url} for submission {submissionid}")

    if r.ok:
        return r.json()
    else:
        logger.debug(f"{r.status_code} - {r.url} - {r.text}")
        return None


def get_experiment(auth, experimentid: int, verbose=False) -> dict:
    """Use the NDA Experiment API to get an experiment.
    Args:
        auth: a requests.auth.HTTPBasicAuth object to connect to NDA.
        experimentid: An NDA collection ID or a list of NDA collection IDs. If None, gets all submissions.
    Returns:
        dict from JSON format.
    """

    r = requests.get(f"https://nda.nih.gov/api/experiment/{experimentid}",
                     auth=auth, headers={'Accept': 'application/json'})

    logger.debug(f"Request {r.url} for experiment {experimentid}")

    if r.ok:
        return r.json()
    else:
        logger.debug(f"{r.status_code} - {r.url} - {r.text}")
        return None

def process_submissions(submission_data):
    """Process NDA submissions from a dictionary of data from the NDA Submission API.
    
    The specific NDA API is the root submission endpoint that gets submissions from specific
    collections.

    Args:
        submission_data: Dictionary of data from NDA Submission API, or from ndasynapse.nda.get_submissions
    Returns:
        Pandas data frame with submission information.
    """

    if submission_data is None:
        logger.debug("No submission data to process.")
        return pandas.DataFrame()

    if not isinstance(submission_data, (list,)):
        submission_data = [submission_data]
    
    submissions =  [dict(collectionid=x['collection']['id'], collectiontitle=x['collection']['title'],
                         submission_id=x['submission_id'], submission_status=x['submission_status'],
                         dataset_title=x['dataset_title']) for x in submission_data]

    return pandas.DataFrame(submissions)

def ndar_central_location(fileobj):
    bucket, key = (fileobj['file_remote_path']
                    .split('//')[1]
                    .split('/', 1))
    return {'Bucket': bucket, 'Key': key}


def nda_bsmn_location(fileobj, collection_id, submission_id):
    original_key = (fileobj['file_remote_path']
                    .split('//')[1]
                    .split('/', 1)[1]
                    .replace('ndar_data/DataSubmissions', 'submission_{}/ndar_data/DataSubmissions'.format(submission_id))
                    )
    nda_bsmn_key = 'collection_{}/{}'.format(collection_id, original_key)
    return {'Bucket': 'nda-bsmn', 'Key': nda_bsmn_key}

def process_submission_files(submission_files):

    submission_files_processed = [dict(id=x['id'], file_type=x['file_type'], 
                                       file_remote_path=x['file_remote_path'],
                                       status=x['status'], md5sum=x['md5sum'], size=x['size'],
                                       created_date=x['created_date'], modified_date=x['modified_date']) for x in submission_files]

    return pandas.DataFrame(submission_files_processed)

def get_collection_ids_from_links(data_structure_row: dict) -> set:
    """Get a set of collection IDs from a data structure row from the NDA GUID API.

    Args:
        data_structure_row: a dictionary from the JSON returned by the NDA GUID data API.
    Returns:
        a set of collection IDs as integers.

    """

    curr_collection_ids = set()
    for link_row in data_structure_row["links"]["link"]:
        if link_row["rel"].lower() == "collection":
            curr_collection_ids.add(int(link_row["href"].split("=")[1]))
    
    if len(curr_collection_ids) > 1:
        logger.warn(f"Found different collection ids: {curr_collection_ids}")

    return curr_collection_ids

def sample_data_files_to_df(guid_data):
    # Get data files from samples.
    tmp = []

    for row in guid_data['age'][0]['dataStructureRow']:

        collection_id = get_collection_ids_from_links(row).pop()
        dataset_id = row['datasetId']
        tmp_row_dict = {'collection_id': collection_id, 'datasetId': dataset_id}

        for col in row['dataElement']:
            tmp_row_dict[col['name']] = col['value']
            if col.get('md5sum') and col.get('size') and col['name'].startswith('DATA_FILE'):
                tmp_row_dict["%s_md5sum" % (col['name'], )] = col['md5sum']
                tmp_row_dict["%s_size" % (col['name'], )] = col['size']
        tmp.append(tmp_row_dict)

    samples = pandas.io.json.json_normalize(tmp)
    # samples['datasetId'] = [x['datasetId'] for x in guid_data['age'][0]['dataStructureRow']]

    return samples

def process_samples(samples):

    colnames_lower = [x.lower() for x in samples.columns.tolist()]
    samples.columns = colnames_lower

    datafile_column_names = samples.filter(regex=r"data_file\d+$").columns.tolist()

    samples_final = pandas.DataFrame()
    sample_columns = [column for column in samples.columns.tolist() if not column.startswith("data_file")]
    
    for col in datafile_column_names:
        keep_cols = sample_columns + [col, f'{col}_type', f'{col}_md5sum', f'{col}_size']
        samples_tmp = samples[keep_cols]

        samples_tmp.rename(columns={col: 'data_file',
                                    f'{col}_type': 'fileFormat',
                                    f'{col}_md5sum': 'md5',
                                    f'{col}_size': 'size'},
                           inplace=True)

        samples_final = pandas.concat([samples_final, samples_tmp], ignore_index=True)

    missing_data_file = samples_final.data_file.isnull()

    missing_files = samples_final.datasetid[missing_data_file].drop_duplicates().tolist()

    if missing_files:
        logger.info("These datasets are missing a data file and will be dropped: %s" % (missing_files,))
        samples_final = samples_final[~missing_data_file]
    
    samples_final['fileFormat'].replace(['BAM', 'FASTQ', 'bam_index'],
                                        ['bam', 'fastq', 'bai'],
                                        inplace=True)

    # Remove initial slash to match what is in manifest file
    samples_final.data_file = samples_final['data_file'].apply(lambda value: value[1:] if not pandas.isnull(value) else value)

    # Remove stuff that isn't part of s3 path
    samples_final.data_file = [str(x).replace("![CDATA[", "").replace("]]>", "") for x in samples_final.data_file.tolist()]

    samples_final = samples_final[samples_final.data_file != 'nan']

    samples_final['species'] = samples_final.organism.replace(['Homo Sapiens'], ['Human'])

    # df.drop(["organism"], axis=1, inplace=True)

    # df = df[SAMPLE_COLUMNS]

    return samples_final


def subjects_to_df(json_data):

    tmp = []

    for row in json_data['age'][0]['dataStructureRow']:
        collection_id = get_collection_ids_from_links(row).pop()

        foo = {col['name']: col['value'] for col in row['dataElement']}
        foo['collection_id'] = collection_id
        tmp.append(foo)

    df = pandas.io.json.json_normalize(tmp)

    colnames_lower = map(lambda x: x.lower(), df.columns.tolist())
    df.columns = colnames_lower

    return df


def process_subjects(df, exclude_genomics_subjects=[]):
    # For some reason there are different ids for this that aren't usable
    # anywhere, so dropping them for now
    # Exclude some subjects
    df = df[~df.genomics_subject02_id.isin(exclude_genomics_subjects)]
    # df.drop(["genomics_subject02_id"], axis=1, inplace=True)

    try:
        df['sex'] = df['sex'].replace(['M', 'F'], ['male', 'female'])
    except KeyError as e:
        logger.error(f"Key 'sex' not found in data frame. Available columns: {df.columns}")
        logger.error(f"Trying to use 'gender' and add new 'sex' column.")
        df['sex'] = df['gender'].replace(['M', 'F'], ['male', 'female'])
        # df = df.drop(labels='gender', axis=1, inplace=True)

    df = df.assign(subject_sample_id_original=df.sample_id_original,
                   subject_biorepository=df.biorepository)

    df.drop(["sample_id_original", "biorepository"], axis=1, inplace=True)

    df = df.drop_duplicates()

    # df = df[SUBJECT_COLUMNS]

    return df


def tissues_to_df(json_data):
    tmp = []
    
    for row in json_data['age'][0]['dataStructureRow']:
        collection_id = get_collection_ids_from_links(row).pop()

        foo = {col['name']: col['value'] for col in row['dataElement']}
        foo['collection_id'] = collection_id
        tmp.append(foo)

    df = pandas.io.json.json_normalize(tmp)

    return df


def process_tissues(df):
    colnames_lower = map(lambda x: x.lower(), df.columns.tolist())
    df.columns = colnames_lower

    df['sex'] = df['sex'].replace(['M', 'F'], ['male', 'female'])

    # This makes them non-unique, so drop them
    # df.drop('nichd_btb02_id', axis=1, inplace=True)

    df = df.drop_duplicates()

    return df


def flattenjson(b, delim):
    val = {}
    for i in b.keys():
        if isinstance(b[i], dict):
            get = flattenjson(b[i], delim)
            for j in get.keys():
                val[i + delim + j] = get[j]
        else:
            val[i] = b[i]

    return val



def get_experiments(auth, experiment_ids, verbose=False):
    df = []

    logger.info("Getting experiments.")

    for experiment_id in experiment_ids:

        data = get_experiment(auth, experiment_id, verbose=verbose)
        data_flat = flattenjson(data[u'omicsOrFMRIOrEEG']['sections'], '.')
        data_flat['experiment_id'] = experiment_id

        df.append(data_flat)


    return df


def process_experiments(d):

    fix_keys = ['processing.processingKits.processingKit',
                'additionalinformation.equipment.equipmentName',
                'extraction.extractionKits.extractionKit',
                'additionalinformation.analysisSoftware.software']

    df = pandas.DataFrame()

    logger.info("Processing experiments.")

    for experiment in d:
    
        for key in fix_keys:
            foo = experiment[key]
            tmp = ",".join(map(lambda x: "%s %s" % (x['vendorName'], x['value']), foo))
            experiment[key] = tmp
    
        foo = experiment['processing.processingProtocols.processingProtocol']
        tmp = ",".join(map(lambda x: "%s: %s" % (x['technologyName'], x['value']), foo))
        experiment['processing.processingProtocols.processingProtocol'] = tmp
        
        experiment['extraction.extractionProtocols.protocolName'] = ",".join(
            experiment['extraction.extractionProtocols.protocolName'])

        logger.debug("Processed experiment %s\n" % (experiment, ))

        expt_df = pandas.DataFrame(experiment, index=experiment.keys())
        
        df = df.append(expt_df, ignore_index=True)
    
    df_change = df[EXPERIMENT_COLUMNS_CHANGE.keys()]
    df_change = df_change.rename(columns=EXPERIMENT_COLUMNS_CHANGE, inplace=False)
    df2 = pandas.concat([df, df_change], axis=1)
    df2 = df2.rename(columns=lambda x: x.replace(".", "_"))
    df2['platform'] = df2['equipmentName'].replace(EQUIPMENT_NAME_REPLACEMENTS,
                                                  inplace=False)

    df2['assay'] = df2['applicationSubType'].replace(APPLICATION_SUBTYPE_REPLACEMENTS,
                                                     inplace=False)

    # Should be fixed at NDA
    df2['assay'][df2['experiment_id'].isin(['675', '777', '778'])] = "targetedSequencing"

    return df2


def merge_tissues_subjects(tissues, subjects):
    """Merge together the tissue file and the subjects file.

    We instituted a standard to use `sample_id_biorepository` in the `genomics_sample03`
    file to map to `sample_id_original` in the `nichd_btb02` file.

    """

    btb_subjects = tissues.merge(subjects, how="left",
                                 left_on=["src_subject_id", "subjectkey", "race", "sex"],
                                 right_on=["src_subject_id", "subjectkey", "race", "sex"])

    # Rename this column to simplify merging with the sample table
    btb_subjects = btb_subjects.assign(sample_id_biorepository=btb_subjects.sample_id_original)

    # Drop this as it will come back from the samples
    btb_subjects.drop('sample_id_original', axis=1, inplace=True)

    return btb_subjects


def merge_tissues_samples(btb_subjects, samples):
    """Merge the tissue/subject with the samples to make a complete metadata table."""

    metadata = samples.merge(btb_subjects, how="left",
                             left_on=["src_subject_id", "subjectkey", "sample_id_biorepository"],
                             right_on=["src_subject_id", "subjectkey", "sample_id_biorepository"])

    metadata = metadata.drop_duplicates()

    return metadata


@deprecated(reason="Should not depend on bucket location to get manifests. Use NDASubmissionFiles class.")
def get_manifests(bucket):
    """Get list of `.manifest` files from the NDA-BSMN bucket.

    Read them in and concatenate them, under the assumption that the files listed
    in the manifest are in the same directory as the manifest file itself.

    """

    manifests = [x for x in bucket.objects.all() if x.key.find('.manifest') >=0]

    manifest = pandas.DataFrame()

    for m in manifests:
        manifest_body = io.BytesIO(m.get()['Body'].read())
        folder = os.path.split(m.key)[0]

        try:
            tmp = pandas.read_csv(manifest_body, delimiter="\t", header=None)
        except pandas.errors.EmptyDataError:
            logger.info("No data in the manifest for %s" % (m,))
            continue

        tmp.columns = MANIFEST_COLUMNS
        tmp.filename = "s3://%s/%s/" % (bucket.name, folder,) + tmp.filename.map(str)
        manifest = pandas.concat([manifest, tmp])

    manifest.reset_index(drop=True, inplace=True)

    return manifest


def merge_metadata_manifest(metadata, manifest):
    metadata_manifest = manifest.merge(metadata, how="left",
                                       left_on="filename",
                                       right_on="data_file")

    metadata_manifest = metadata_manifest.drop_duplicates()

    return metadata_manifest


def find_duplicate_filenames(metadata):
    """Find duplicates based on the basename of the data_file column.

    """
    basenames = metadata.data_file.apply(lambda x: os.path.basename(x))
    counts = basenames.value_counts()

    duplicates = counts[counts > 1].index

    return (metadata[~basenames.isin(duplicates)],
            metadata[basenames.isin(duplicates)])

def get_manifest_file_data(data_files, manifest_type):
    for data_file in data_files:

        data_file_as_string = data_file["content"].decode("utf-8")

        if manifest_type in data_file_as_string:
            manifest_df = pandas.read_csv(io.StringIO(data_file_as_string), skiprows=1)
            return manifest_df

    return None    

class NDASubmissionFiles:

    ASSOCIATED_FILE = 'Submission Associated File'
    DATA_FILE = 'Submission Data File'
    MANIFEST_FILE = 'Submission Manifest File'
    SUBMISSION_PACKAGE = 'Submission Data Package'
    SUBMISSION_TICKET = 'Submission Ticket'
    SUBMISSION_MEMENTO = 'Submission Memento'

    logger = logging.getLogger('NDASubmissionFiles')
    logger.setLevel(logging.INFO)

    def __init__(self, config, files, collection_id, submission_id):
        self.config = config # ApplicationProperties().get_config
        self.auth = (self.config.get('username'),
                     self.config.get('password'))
        self.headers = {'Accept': 'application/json'}
        self.collection_id = str(collection_id)
        self.submission_id = str(submission_id)
        
        (self.associated_files,
         self.data_files,
         self.manifest_file,
         self.submission_package,
         self.submission_ticket,
         self.submission_memento) = self.get_nda_submission_file_types(files)
        
        self.bsmn_locations = [nda_bsmn_location(x, self.collection_id, self.submission_id) for x in files]

        self.debug = True

    def get_nda_submission_file_types(self, files):
        associated_files = []
        data_files = []
        manifest_file = []
        submission_package = []
        submission_ticket = []
        submission_memento = []

        for file in files:
            if file['file_type'] == self.ASSOCIATED_FILE:
                associated_files.append({'name': file})
            elif file['file_type'] == self.DATA_FILE:
                data_files.append({'name': file,
                                   'content': self.read_file(file)})
            elif file['file_type'] == self.MANIFEST_FILE:
                manifest_file.append({'name': file,
                                      'content': self.read_file(file)})
            elif file['file_type'] == self.SUBMISSION_PACKAGE:
                submission_package.append(file)
            elif file['file_type'] == self.SUBMISSION_TICKET:
                submission_ticket.append({'name': file,
                                          'content': self.read_file(file)})
            elif file['file_type'] == self.SUBMISSION_MEMENTO:
                submission_memento.append({'name': file,
                                           'content': self.read_file(file)})

        return (associated_files,
                data_files,
                manifest_file,
                submission_package,
                submission_ticket,
                submission_memento)

    def read_file(self, submission_file):
        download_url = submission_file['_links']['download']['href']
        request = requests.get(download_url, auth=self.auth)

        return request.content

    def manifest_to_df(self, short_name):
        """Read the contents of a data file of the type given by the short name.

        Args:
            short_name: An NDA short name for a manifest type (like 'genomics_sample03').
        Returns:
            Pandas data frame, or None if no data file found.
        """
        logger.warning("Information in the submission manifests may be out of date with respect to the NDA database.")

        for data_file in self.data_files:
            data_file_as_string = data_file['content'].decode('utf-8')
            if short_name in data_file_as_string:
                data = pandas.read_csv(io.StringIO(data_file_as_string), skiprows=1)
                return data

        return None

class NDASubmission:

    _subject_manifest = "genomics_subject"
    _sample_manifest = "genomics_sample"

    logger = logging.getLogger('NDASubmission')
    logger.setLevel(logging.INFO)

    def __init__(self, config, submission_id):

        self.config = config # ApplicationProperties().get_config
        self.auth = (self.config.get('username'),
                     self.config.get('password'))
        self.submission_id = str(submission_id)
        self.submission = get_submission(auth=self.auth, submissionid=submission_id)

        if self.submission is None:
            self.logger.error(f"Could not retrieve submission {self.submission_id}.")
            self.processed_submissions = None
            self.submission_files = None
            self.guids = set()
        else:
            self.processed_submission = process_submissions(submission_data=self.submission)
            self.submission_files = self.get_submission_files()
            self.guids = self.get_guids()
            self.logger.info(f"Got submission {self.submission_id}.")

    def get_submission_files(self):
        submission_id = str(self.submission['submission_id'])
        collection_id = str(self.submission['collection']['id'])

        files = get_submission_files(auth=self.auth, submissionid=submission_id)
        processed_files = process_submission_files(submission_files=files)
        processed_files['submission_id'] = submission_id
        processed_files['collection_id'] = collection_id

        submission_files = {'files': NDASubmissionFiles(self.config, files, collection_id, submission_id),
                            'processed_files': processed_files,
                            'collection_id': collection_id,
                            'submission_id': submission_id}

        return submission_files


    def get_guids(self):
        """Get a list of GUIDs for each submission from the genomics subject manifest data file.
        
        This requires looking inside the submission-associated data file to find the GUIDs.
        It is prone to issues of being outdated due to submission edits. It 

        """
        logger.warning("GUID information comes from the submission manifests may be out of date with respect to the NDA database.")

        guids = set()

        submission_data_files = self.submission_files["files"].data_files
        manifest_df = get_manifest_file_data(submission_data_files, 
                                             self._sample_manifest)

        if manifest_df is None:
            self.logger.debug(f"No {self._sample_manifest} manifest for submission {self.submission_id}. Looking for the {self._subject_manifest} manifest.")
            manifest_df = get_manifest_file_data(submission_data_files, 
                                                 self._subject_manifest)

        if manifest_df is not None:
            try:
                guids_found = manifest_df["subjectkey"].tolist()
                self.logger.debug(f"Adding {len(guids_found)} GUIDS for submission {self.submission_id}.")
                guids.update(guids_found)
            except KeyError:
                self.logger.error(f"Manifest for submission {self.submission_id} had no guid (subjectkey) column.")
        else:
            self.logger.info(f"No manifest with GUIDs found for submission {self.submission_id}")

        return guids


class NDACollection(object):

    _subject_manifest = "genomics_subject"
    _sample_manifest = "genomics_sample"

    logger = logging.getLogger('NDACollection')
    logger.setLevel(logging.INFO)

    def __init__(self, config, collection_id=None):

        self.config = config # ApplicationProperties().get_config
        self.auth = (self.config.get('username'),
                     self.config.get('password'))
        self.collection_id = str(collection_id)

        self._collection_submissions = get_submissions(auth=self.auth, 
                                                       collectionid = self.collection_id)

        self.logger.info(f"Getting {len(self._collection_submissions)} submissions for collection {self.collection_id}.")
        
        self.submissions = [NDASubmission(config, submission_id=sub['submission_id']) for sub in self._collection_submissions if sub is not None]

        self.submission_files = self.get_submission_files()
        self.guids = self.get_guids()
        self.logger.info(f"Got collection {self.collection_id}.")

    def get_submission_files(self):
        submission_files = []
        for submission in self.submissions:
            if submission.submission_files is not None:
                submission_files.extend(submission.submission_files)
        return submission_files


    def get_guids(self):
        """Get a list of GUIDs for each submission from the genomics subject manifest data file.
        
        This requires looking inside the submission-associated data file to find the GUIDs.
        It is prone to issues of being outdated due to submission edits. It 

        """
        logger.warning("GUID information comes from the submission manifests may be out of date with respect to the NDA database.")

        guids = set()
        for submission in self.submissions:
            guids.update(submission.guids)

        return guids
        
    def get_collection_manifests(self, manifest_type):
        """Get all original manifests submitted with each submission in a collection.

        NDA does not update these files if metadata change requests are made.
        They only update metadata in their database, accessible through the GUID API.
        Records obtained here should be used for historical purposes only.

        Args:
            manifest_type: An NDA manifest type, like 'genomics_sample'.
        Returns:
            A pandas data frame of all submission manifests concatenated together.
        """

        logger.warning("Information in the collection manifests may be out of date.")
        
        all_data = []

        for submission in self.submissions:
            
            try:
                ndafiles = submission.submission_files['files']
            except IndexError:
                logger.info(f"No submission files for collection {coll_id}.")
                continue

            manifest_data = ndafiles.manifest_to_df(manifest_type)

            if manifest_data is not None and manifest_data.shape[0] > 0:
                manifest_data['collection_id'] = str(self.collection_id)
                manifest_data['submission_id'] = str(submission.submission_id)
                all_data.append(manifest_data)
            else:
                logger.info(f"No {manifest_type} data found for submission {submission.submission_id}.")
        
        if all_data:
            all_data_df = pandas.concat(all_data, axis=0, ignore_index=True, sort=False)
            return all_data_df

        return pandas.DataFrame()
