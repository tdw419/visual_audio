/*
 * GStreamer plugin for Visual Audio (.upic.json) format playback
 * 
 * This plugin parses UPIC JSON projects and synthesizes audio in real-time
 * for playback in GStreamer-compatible music players.
 */

#include <gst/gst.h>
#include <gst/base/gstpushsrc.h>
#include <json-c/json.h>
#include <math.h>
#include <string.h>

GST_DEBUG_CATEGORY_STATIC (gst_upic_debug);
#define GST_CAT_DEFAULT gst_upic_debug

/* Filter signals and args */
enum {
  LAST_SIGNAL
};

enum {
  ARG_0,
  ARG_LOCATION
};

#define DEFAULT_SAMPLE_RATE 44100
#define DEFAULT_CHANNELS 2
#define BLOCK_SIZE 4096

/* UPIC Envelope structure */
typedef struct {
    char *name;
    int num_points;
    double *times;
    double *values;
} UPICEnvelope;

/* UPIC Wavetable structure */
typedef struct {
    char *name;
    int length;
    double *samples;
    double sample_rate;
} UPICWavetable;

/* UPIC Voice structure */
typedef struct {
    char *name;
    UPICWavetable *wavetable;
    double base_frequency;
    double base_amplitude;
    UPICEnvelope *freq_envelope;
    UPICEnvelope *amp_envelope;
    UPICEnvelope *time_envelope;
    double phase;
} UPICVoice;

/* UPIC Project structure */
typedef struct {
    char *name;
    int num_wavetables;
    UPICWavetable **wavetables;
    int num_envelopes;
    UPICEnvelope **envelopes;
    int num_voices;
    UPICVoice **voices;
} UPICProject;

/* GObject boilerplate */
#define GST_TYPE_UPIC_DEC \
  (gst_upic_dec_get_type())
#define GST_UPIC_DEC(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj),GST_TYPE_UPIC_DEC,GstUpicDec))
#define GST_UPIC_DEC_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST((klass),GST_TYPE_UPIC_DEC,GstUpicDecClass))
#define GST_IS_UPIC_DEC(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE((obj),GST_TYPE_UPIC_DEC))
#define GST_IS_UPIC_DEC_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE((klass),GST_TYPE_UPIC_DEC))

typedef struct _GstUpicDec GstUpicDec;
typedef struct _GstUpicDecClass GstUpicDecClass;

/* Pad templates */
static GstStaticPadTemplate gst_upic_dec_src_template =
GST_STATIC_PAD_TEMPLATE ("src",
    GST_PAD_SRC,
    GST_PAD_ALWAYS,
    GST_STATIC_CAPS ("audio/x-raw, "
        "format = (string) F32LE, "
        "rate = (int) 44100, "
        "channels = (int) 2, "
        "layout = (string) interleaved")
    );

struct _GstUpicDec {
    GstPushSrc element;
    
    /* Pad */
    GstPad *srcpad;
    
    /* File handling */
    gchar *location;
    UPICProject *project;
    FILE *file;
    
    /* Audio parameters */
    gint sample_rate;
    gint channels;
    
    /* Playback state */
    gdouble current_time;
    gint64 samples_generated;
    GstClockTime timestamp;
    gboolean eos;
};

struct _GstUpicDecClass {
    GstPushSrcClass parent_class;
};

/* Forward declarations */
static void gst_upic_dec_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec);
static void gst_upic_dec_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec);
static void gst_upic_dec_finalize (GObject * object);
static gboolean gst_upic_dec_start (GstBaseSrc * basesrc);
static gboolean gst_upic_dec_stop (GstBaseSrc * basesrc);
static GstFlowReturn gst_upic_dec_create (GstPushSrc * psrc, GstBuffer ** buf);
static gboolean gst_upic_dec_query (GstBaseSrc * src, GstQuery * query);
static gboolean gst_upic_dec_is_seekable (GstBaseSrc * src);
static gboolean gst_upic_dec_do_seek (GstBaseSrc * src, GstSegment * segment);

/* Helper function: linear interpolation */
static double
interpolate_linear (double t, double *times, double *values, int num_points)
{
    if (num_points == 1)
        return values[0];
    
    if (t <= times[0])
        return values[0];
    if (t >= times[num_points - 1])
        return values[num_points - 1];
    
    int i;
    for (i = 0; i < num_points - 1; i++) {
        if (times[i] <= t && t <= times[i + 1]) {
            double t1 = times[i];
            double t2 = times[i + 1];
            double v1 = values[i];
            double v2 = values[i + 1];
            double fraction = (t - t1) / (t2 - t1);
            return v1 + fraction * (v2 - v1);
        }
    }
    
    return values[num_points - 1];
}

/* Helper function: get interpolated wavetable sample */
static double
wavetable_get_sample (UPICWavetable * wt, double phase)
{
    phase = fmod (phase, 1.0);
    if (phase < 0.0)
        phase += 1.0;
    
    double position = phase * (wt->length - 1);
    int index_floor = (int) floor (position);
    int index_ceil = MIN (index_floor + 1, wt->length - 1);
    double fraction = position - index_floor;
    
    double sample_floor = wt->samples[index_floor];
    double sample_ceil = wt->samples[index_ceil];
    
    return (1.0 - fraction) * sample_floor + fraction * sample_ceil;
}

/* Synthesize audio for one sample */
static void
synthesize_sample (GstUpicDec * dec, double *left, double *right)
{
    UPICProject *proj = dec->project;
    double l = 0.0, r = 0.0;
    
    /* Normalize time to [0, 1] for envelope evaluation */
    double env_time = dec->current_time / 10.0;  /* Assume 10s duration default */
    if (env_time > 1.0)
        env_time = 1.0;
    
    for (int v = 0; v < proj->num_voices; v++) {
        UPICVoice *voice = proj->voices[v];
        
        if (!voice->wavetable)
            continue;
        
        /* Get envelope values */
        double freq_scale = 1.0;
        if (voice->freq_envelope)
            freq_scale = interpolate_linear (env_time, voice->freq_envelope->times,
                                           voice->freq_envelope->values,
                                           voice->freq_envelope->num_points);
        
        double amp_scale = 1.0;
        if (voice->amp_envelope)
            amp_scale = interpolate_linear (env_time, voice->amp_envelope->times,
                                           voice->amp_envelope->values,
                                           voice->amp_envelope->num_points);
        
        double time_scale = 1.0;
        if (voice->time_envelope)
            time_scale = interpolate_linear (env_time, voice->time_envelope->times,
                                            voice->time_envelope->values,
                                            voice->time_envelope->num_points);
        
        /* Calculate effective frequency */
        double frequency = voice->base_frequency * freq_scale;
        
        /* Update phase */
        double phase_increment = frequency / (double) dec->sample_rate;
        voice->phase += phase_increment * time_scale;
        
        /* Get wavetable sample */
        double sample = wavetable_get_sample (voice->wavetable, voice->phase);
        
        /* Apply amplitude */
        double amplitude = voice->base_amplitude * amp_scale;
        sample *= amplitude;
        
        /* Mix to stereo */
        l += sample;
        r += sample;
    }
    
    /* Normalize to prevent clipping */
    if (proj->num_voices > 0) {
        l /= (double) proj->num_voices;
        r /= (double) proj->num_voices;
    }
    
    *left = l;
    *right = r;
}

/* Parse JSON envelope */
static UPICEnvelope *
parse_envelope (json_object * env_obj)
{
    UPICEnvelope *env = g_malloc0 (sizeof (UPICEnvelope));
    
    json_object *name_obj;
    json_object_object_get_ex (env_obj, "name", &name_obj);
    env->name = g_strdup (json_object_get_string (name_obj));
    
    json_object *points_obj;
    if (json_object_object_get_ex (env_obj, "control_points", &points_obj)) {
        env->num_points = json_object_array_length (points_obj);
        env->times = g_malloc (env->num_points * sizeof (double));
        env->values = g_malloc (env->num_points * sizeof (double));
        
        for (int i = 0; i < env->num_points; i++) {
            json_object *point = json_object_array_get_idx (points_obj, i);
            json_object *time_obj = json_object_array_get_idx (point, 0);
            json_object *value_obj = json_object_array_get_idx (point, 1);
            
            env->times[i] = json_object_get_double (time_obj);
            env->values[i] = json_object_get_double (value_obj);
        }
    } else {
        env->num_points = 1;
        env->times = g_malloc (sizeof (double));
        env->values = g_malloc (sizeof (double));
        env->times[0] = 0.0;
        env->values[0] = 1.0;
    }
    
    return env;
}

/* Parse JSON wavetable */
static UPICWavetable *
parse_wavetable (json_object * wt_obj)
{
    UPICWavetable *wt = g_malloc0 (sizeof (UPICWavetable));
    
    json_object *name_obj;
    json_object_object_get_ex (wt_obj, "name", &name_obj);
    wt->name = g_strdup (json_object_get_string (name_obj));
    
    json_object *samples_obj;
    json_object_object_get_ex (wt_obj, "samples", &samples_obj);
    wt->length = json_object_array_length (samples_obj);
    wt->samples = g_malloc (wt->length * sizeof (double));
    
    for (int i = 0; i < wt->length; i++) {
        json_object *sample_obj = json_object_array_get_idx (samples_obj, i);
        wt->samples[i] = json_object_get_double (sample_obj);
    }
    
    json_object *rate_obj;
    if (json_object_object_get_ex (wt_obj, "sample_rate", &rate_obj)) {
        wt->sample_rate = json_object_get_double (rate_obj);
    } else {
        wt->sample_rate = 44100.0;
    }
    
    return wt;
}

/* Parse JSON voice */
static UPICVoice *
parse_voice (json_object * voice_obj, UPICProject * proj)
{
    UPICVoice *voice = g_malloc0 (sizeof (UPICVoice));
    
    json_object *name_obj;
    json_object_object_get_ex (voice_obj, "name", &name_obj);
    voice->name = g_strdup (json_object_get_string (name_obj));
    
    /* Get wavetable */
    json_object *wt_name_obj;
    if (json_object_object_get_ex (voice_obj, "wavetable_name", &wt_name_obj)) {
        const char *wt_name = json_object_get_string (wt_name_obj);
        for (int i = 0; i < proj->num_wavetables; i++) {
            if (strcmp (proj->wavetables[i]->name, wt_name) == 0) {
                voice->wavetable = proj->wavetables[i];
                break;
            }
        }
    }
    
    /* Get basic parameters */
    json_object *freq_obj;
    if (json_object_object_get_ex (voice_obj, "base_frequency", &freq_obj)) {
        voice->base_frequency = json_object_get_double (freq_obj);
    } else {
        voice->base_frequency = 440.0;
    }
    
    json_object *amp_obj;
    if (json_object_object_get_ex (voice_obj, "base_amplitude", &amp_obj)) {
        voice->base_amplitude = json_object_get_double (amp_obj);
    } else {
        voice->base_amplitude = 0.5;
    }
    
    /* Get envelopes */
    json_object *env_obj;
    if (json_object_object_get_ex (voice_obj, "frequency_envelope", &env_obj)) {
        const char *env_name = json_object_get_string (env_obj);
        for (int i = 0; i < proj->num_envelopes; i++) {
            if (strcmp (proj->envelopes[i]->name, env_name) == 0) {
                voice->freq_envelope = proj->envelopes[i];
                break;
            }
        }
    }
    
    if (json_object_object_get_ex (voice_obj, "amplitude_envelope", &env_obj)) {
        const char *env_name = json_object_get_string (env_obj);
        for (int i = 0; i < proj->num_envelopes; i++) {
            if (strcmp (proj->envelopes[i]->name, env_name) == 0) {
                voice->amp_envelope = proj->envelopes[i];
                break;
            }
        }
    }
    
    if (json_object_object_get_ex (voice_obj, "time_scaling_envelope", &env_obj)) {
        const char *env_name = json_object_get_string (env_obj);
        for (int i = 0; i < proj->num_envelopes; i++) {
            if (strcmp (proj->envelopes[i]->name, env_name) == 0) {
                voice->time_envelope = proj->envelopes[i];
                break;
            }
        }
    }
    
    voice->phase = 0.0;
    
    return voice;
}

/* Load UPIC project from JSON file */
static UPICProject *
load_upic_project (const char *filename)
{
    FILE *f = fopen (filename, "r");
    if (!f) {
        GST_ERROR ("Could not open file: %s", filename);
        return NULL;
    }
    
    fseek (f, 0, SEEK_END);
    long length = ftell (f);
    fseek (f, 0, SEEK_SET);
    
    char *buffer = g_malloc (length + 1);
    fread (buffer, 1, length, f);
    buffer[length] = '\0';
    fclose (f);
    
    json_object *root = json_tokener_parse (buffer);
    g_free (buffer);
    
    if (!root) {
        GST_ERROR ("Could not parse JSON");
        return NULL;
    }
    
    UPICProject *proj = g_malloc0 (sizeof (UPICProject));
    
    /* Parse project name */
    json_object *name_obj;
    if (json_object_object_get_ex (root, "name", &name_obj)) {
        proj->name = g_strdup (json_object_get_string (name_obj));
    } else {
        proj->name = g_strdup ("Untitled");
    }
    
    /* Parse wavetables */
    json_object *wt_array;
    if (json_object_object_get_ex (root, "wavetables", &wt_array)) {
        proj->num_wavetables = json_object_array_length (wt_array);
        proj->wavetables = g_malloc (proj->num_wavetables * sizeof (UPICWavetable *));
        
        for (int i = 0; i < proj->num_wavetables; i++) {
            json_object *wt_obj = json_object_array_get_idx (wt_array, i);
            proj->wavetables[i] = parse_wavetable (wt_obj);
        }
    } else {
        proj->num_wavetables = 0;
        proj->wavetables = NULL;
    }
    
    /* Parse envelopes */
    json_object *env_array;
    if (json_object_object_get_ex (root, "envelopes", &env_array)) {
        proj->num_envelopes = json_object_array_length (env_array);
        proj->envelopes = g_malloc (proj->num_envelopes * sizeof (UPICEnvelope *));
        
        for (int i = 0; i < proj->num_envelopes; i++) {
            json_object *env_obj = json_object_array_get_idx (env_array, i);
            proj->envelopes[i] = parse_envelope (env_obj);
        }
    } else {
        proj->num_envelopes = 0;
        proj->envelopes = NULL;
    }
    
    /* Parse voices */
    json_object *voice_array;
    if (json_object_object_get_ex (root, "voices", &voice_array)) {
        proj->num_voices = json_object_array_length (voice_array);
        proj->voices = g_malloc (proj->num_voices * sizeof (UPICVoice *));
        
        for (int i = 0; i < proj->num_voices; i++) {
            json_object *voice_obj = json_object_array_get_idx (voice_array, i);
            proj->voices[i] = parse_voice (voice_obj, proj);
        }
    } else {
        proj->num_voices = 0;
        proj->voices = NULL;
    }
    
    json_object_put (root);
    
    GST_INFO ("Loaded UPIC project: %s (%d wavetables, %d envelopes, %d voices)",
              proj->name, proj->num_wavetables, proj->num_envelopes, proj->num_voices);
    
    return proj;
}

/* Free UPIC project */
static void
free_upic_project (UPICProject * proj)
{
    if (!proj)
        return;
    
    g_free (proj->name);
    
    for (int i = 0; i < proj->num_wavetables; i++) {
        g_free (proj->wavetables[i]->name);
        g_free (proj->wavetables[i]->samples);
        g_free (proj->wavetables[i]);
    }
    g_free (proj->wavetables);
    
    for (int i = 0; i < proj->num_envelopes; i++) {
        g_free (proj->envelopes[i]->name);
        g_free (proj->envelopes[i]->times);
        g_free (proj->envelopes[i]->values);
        g_free (proj->envelopes[i]);
    }
    g_free (proj->envelopes);
    
    for (int i = 0; i < proj->num_voices; i++) {
        g_free (proj->voices[i]->name);
        g_free (proj->voices[i]);
    }
    g_free (proj->voices);
    
    g_free (proj);
}

/* GObject class initialization */
G_DEFINE_TYPE (GstUpicDec, gst_upic_dec, GST_TYPE_PUSH_SRC);

static void
gst_upic_dec_class_init (GstUpicDecClass * klass)
{
    GObjectClass *gobject_class = G_OBJECT_CLASS (klass);
    GstElementClass *gstelement_class = GST_ELEMENT_CLASS (klass);
    GstBaseSrcClass *gstbasesrc_class = GST_BASE_SRC_CLASS (klass);
    GstPushSrcClass *gstpushsrc_class = GST_PUSH_SRC_CLASS (klass);
    
    gobject_class->set_property = gst_upic_dec_set_property;
    gobject_class->get_property = gst_upic_dec_get_property;
    gobject_class->finalize = gst_upic_dec_finalize;
    
    g_object_class_install_property (gobject_class, ARG_LOCATION,
        g_param_spec_string ("location", "File Location",
            "Location of the UPIC JSON file to read", NULL,
            G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS));
    
    gstbasesrc_class->start = GST_DEBUG_FUNCPTR (gst_upic_dec_start);
    gstbasesrc_class->stop = GST_DEBUG_FUNCPTR (gst_upic_dec_stop);
    gstbasesrc_class->is_seekable = GST_DEBUG_FUNCPTR (gst_upic_dec_is_seekable);
    gstbasesrc_class->do_seek = GST_DEBUG_FUNCPTR (gst_upic_dec_do_seek);
    gstbasesrc_class->query = GST_DEBUG_FUNCPTR (gst_upic_dec_query);
    
    gstpushsrc_class->create = GST_DEBUG_FUNCPTR (gst_upic_dec_create);
    
    gst_element_class_set_static_metadata (gstelement_class,
        "UPIC Decoder", "Decoder/Audio",
        "Decodes Visual Audio UPIC JSON projects to audio",
        "Jericho <tdw419@github.com>");
    
    gst_element_class_add_pad_template (gstelement_class,
        gst_static_pad_template_get (&gst_upic_dec_src_template));
}

static void
gst_upic_dec_init (GstUpicDec * dec)
{
    dec->location = NULL;
    dec->project = NULL;
    dec->sample_rate = DEFAULT_SAMPLE_RATE;
    dec->channels = DEFAULT_CHANNELS;
    dec->current_time = 0.0;
    dec->samples_generated = 0;
    dec->timestamp = GST_CLOCK_TIME_NONE;
    dec->eos = FALSE;
    
    gst_base_src_set_live (GST_BASE_SRC (dec), FALSE);
    gst_base_src_set_format (GST_BASE_SRC (dec), GST_FORMAT_TIME);
}

static void
gst_upic_dec_finalize (GObject * object)
{
    GstUpicDec *dec = GST_UPIC_DEC (object);
    
    g_free (dec->location);
    if (dec->project) {
        free_upic_project (dec->project);
    }
    
    G_OBJECT_CLASS (gst_upic_dec_parent_class)->finalize (object);
}

static void
gst_upic_dec_set_property (GObject * object, guint prop_id,
    const GValue * value, GParamSpec * pspec)
{
    GstUpicDec *dec = GST_UPIC_DEC (object);
    
    switch (prop_id) {
        case ARG_LOCATION:
            g_free (dec->location);
            dec->location = g_value_dup_string (value);
            break;
        default:
            G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
            break;
    }
}

static void
gst_upic_dec_get_property (GObject * object, guint prop_id,
    GValue * value, GParamSpec * pspec)
{
    GstUpicDec *dec = GST_UPIC_DEC (object);
    
    switch (prop_id) {
        case ARG_LOCATION:
            g_value_set_string (value, dec->location);
            break;
        default:
            G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
            break;
    }
}

static gboolean
gst_upic_dec_start (GstBaseSrc * basesrc)
{
    GstUpicDec *dec = GST_UPIC_DEC (basesrc);
    
    if (!dec->location) {
        GST_ELEMENT_ERROR (dec, RESOURCE, NOT_FOUND,
            ("No location specified"), (NULL));
        return FALSE;
    }
    
    dec->project = load_upic_project (dec->location);
    if (!dec->project) {
        GST_ELEMENT_ERROR (dec, RESOURCE, READ,
            ("Could not load UPIC project from %s", dec->location), (NULL));
        return FALSE;
    }
    
    dec->current_time = 0.0;
    dec->samples_generated = 0;
    dec->timestamp = 0;
    dec->eos = FALSE;
    
    /* Set up output caps */
    GstCaps *caps = gst_caps_new_simple ("audio/x-raw",
        "format", G_TYPE_STRING, "F32LE",
        "rate", G_TYPE_INT, dec->sample_rate,
        "channels", G_TYPE_INT, dec->channels,
        "layout", G_TYPE_STRING, "interleaved",
        NULL);
    
    gst_pad_set_caps (GST_BASE_SRC_PAD (basesrc), caps);
    gst_caps_unref (caps);
    
    GST_INFO ("Started UPIC decoder: %s", dec->location);
    
    return TRUE;
}

static gboolean
gst_upic_dec_stop (GstBaseSrc * basesrc)
{
    GstUpicDec *dec = GST_UPIC_DEC (basesrc);
    
    if (dec->project) {
        free_upic_project (dec->project);
        dec->project = NULL;
    }
    
    GST_INFO ("Stopped UPIC decoder");
    
    return TRUE;
}

static GstFlowReturn
gst_upic_dec_create (GstPushSrc * psrc, GstBuffer ** buf)
{
    GstUpicDec *dec = GST_UPIC_DEC (psrc);
    
    if (dec->eos) {
        return GST_FLOW_EOS;
    }
    
    /* Allocate buffer */
    gsize buffer_size = BLOCK_SIZE * dec->channels * sizeof (float);
    GstBuffer *buffer = gst_buffer_new_and_alloc (buffer_size);
    GstMapInfo map;
    
    if (!gst_buffer_map (buffer, &map, GST_MAP_WRITE)) {
        gst_buffer_unref (buffer);
        return GST_FLOW_ERROR;
    }
    
    float *data = (float *) map.data;
    int samples_written = 0;
    
    /* Synthesize audio */
    for (int i = 0; i < BLOCK_SIZE; i++) {
        double left, right;
        synthesize_sample (dec, &left, &right);
        
        data[i * 2] = (float) left;
        data[i * 2 + 1] = (float) right;
        
        dec->current_time += 1.0 / (double) dec->sample_rate;
        dec->samples_generated++;
        samples_written++;
        
        /* End after 10 seconds (adjustable) */
        if (dec->current_time >= 10.0) {
            dec->eos = TRUE;
            break;
        }
    }
    
    gst_buffer_unmap (buffer, &map);
    
    /* Set buffer metadata */
    GST_BUFFER_PTS (buffer) = dec->timestamp;
    GST_BUFFER_DURATION (buffer) = gst_util_uint64_scale_int (samples_written,
        GST_SECOND, dec->sample_rate);
    dec->timestamp += GST_BUFFER_DURATION (buffer);
    
    *buf = buffer;
    
    return GST_FLOW_OK;
}

static gboolean
gst_upic_dec_query (GstBaseSrc * src, GstQuery * query)
{
    GstUpicDec *dec = GST_UPIC_DEC (src);
    gboolean res = FALSE;
    
    switch (GST_QUERY_TYPE (query)) {
        case GST_QUERY_DURATION:
        {
            GstFormat format;
            gst_query_parse_duration (query, &format, NULL);
            
            if (format == GST_FORMAT_TIME) {
                /* Default 10 second duration */
                gst_query_set_duration (query, format, 10 * GST_SECOND);
                res = TRUE;
            }
            break;
        }
        case GST_QUERY_POSITION:
        {
            GstFormat format;
            gst_query_parse_position (query, &format, NULL);
            
            if (format == GST_FORMAT_TIME) {
                gst_query_set_position (query, format, dec->timestamp);
                res = TRUE;
            }
            break;
        }
        default:
            res = GST_BASE_SRC_CLASS (gst_upic_dec_parent_class)->query (src, query);
            break;
    }
    
    return res;
}

static gboolean
gst_upic_dec_is_seekable (GstBaseSrc * src)
{
    return TRUE;
}

static gboolean
gst_upic_dec_do_seek (GstBaseSrc * src, GstSegment * segment)
{
    GstUpicDec *dec = GST_UPIC_DEC (src);
    
    /* Convert time to sample position */
    dec->timestamp = segment->start;
    dec->current_time = (double) segment->start / GST_SECOND;
    
    /* Reset voice phases for clean seek */
    if (dec->project) {
        for (int i = 0; i < dec->project->num_voices; i++) {
            dec->project->voices[i]->phase = 0.0;
        }
    }
    
    GST_DEBUG ("Seeked to %" GST_TIME_FORMAT, GST_TIME_ARGS (segment->start));
    
    return TRUE;
}

/* Plugin initialization */
static gboolean
plugin_init (GstPlugin * plugin)
{
    GST_DEBUG_CATEGORY_INIT (gst_upic_debug, "upic", 0, "UPIC Decoder");
    
    return gst_element_register (plugin, "upicdec", GST_RANK_NONE,
        GST_TYPE_UPIC_DEC);
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR, GST_VERSION_MINOR, upic,
    "Visual Audio UPIC plugin", plugin_init, VERSION, "LGPL",
    "Visual Audio", "https://github.com/tdw419/visual_audio")