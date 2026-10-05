"""Public workload bounds and nondestructive local recovery I/O boundaries."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from model_release_assurance.production_capacity import contracts as c,io


class CapacityContractsTests(unittest.TestCase):
    def test_fixed_plan_owned_and_agency_targets_open(self):
        plan=c.workload_plan();digest=c.workload_plan_sha256()
        self.assertEqual(plan["io_target_bytes"],[1048576,8388608,33554432])
        self.assertEqual(plan["job_concurrency"],[1,2,4])
        self.assertIsNone(plan["agency_peak_load"])
        plan["io_target_bytes"].append(2**60)
        self.assertEqual(c.workload_plan_sha256(),digest)
        with self.assertRaises(TypeError):
            c.WORKLOAD_PLAN["agency_peak_load"]=1

    def test_profile_is_exact_and_non_authorizing(self):
        c.require_local("local_public_fixture")
        for profile in ("agency_private_cloud",None,True,"local_public_fixture ",{}):
            with self.assertRaises(c.CapacityError):
                c.require_local(profile)
        self.assertTrue(c.FLAGS["local_public_fixture"])
        for name,value in c.FLAGS.items():
            if name!="local_public_fixture":
                self.assertIs(value,False)

    def test_percentiles_use_nearest_rank_and_no_population_claim(self):
        result=c.percentiles([100,1,25,8])
        self.assertEqual((result["min_ns"],result["p50_ns"],result["p95_ns"],result["max_ns"]),(1,8,100,100))
        self.assertEqual(result["sample_count"],4)
        self.assertIs(result["population_inference"],False)
        self.assertEqual(c.percentiles([5])["p95_ns"],5)

    def test_metrics_reject_empty_alias_float_negative_oversize(self):
        for samples in ([],(1,),[True],[1.2],[-1],[2**53],[0]*4097):
            with self.assertRaises(c.CapacityError):
                c.percentiles(samples)

    def test_json_rejects_duplicate_float_infinite_and_custom_values(self):
        for raw in (b'{"n":0,"n":1}',b'{"n":0.1}',b'{"n":NaN}'):
            with self.assertRaises(c.CapacityError):
                c.strict_json(raw)
        for value in ({"n":object()},{"n":(1,)},{"n":2**53}):
            with self.assertRaises(c.CapacityError):
                c.canonical_bytes(value)

    def test_exact_opaque_ids_and_hashes(self):
        self.assertEqual(c.hex_id("a"*32),"a"*32)
        self.assertEqual(c.validate_digest("b"*64),"b"*64)
        for value in (None,"PRIVATE-CANARY","A"*32):
            with self.assertRaises(c.CapacityError) as denied:
                c.hex_id(value)
            self.assertNotIn("PRIVATE",str(denied.exception))


class CapacityIOTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix="mra-capacity-io-")
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def test_new_directory_write_read_exact_and_no_overwrite(self):
        output=io.fresh_directory(self.root/"fresh")
        p=io.exclusive_write(output/"fixture",b"public")
        self.assertEqual(io.read_file(p,6),b"public")
        with self.assertRaises(c.CapacityError):
            io.exclusive_write(p,b"changed")
        with self.assertRaises(c.CapacityError):
            io.fresh_directory(output)
        self.assertEqual(p.read_bytes(),b"public")

    def test_missing_paths_are_generic_not_echoed(self):
        with self.assertRaises(c.CapacityError) as denied:
            io.read_file(self.root/"PRIVATE-CANARY"/"missing")
        self.assertNotIn("PRIVATE-CANARY",str(denied.exception))

    def test_traversal_output_is_refused_without_sibling_write(self):
        (self.root/"existing").mkdir()
        with self.assertRaises(c.CapacityError):
            io.fresh_directory(self.root/"existing"/".."/"escaped")
        self.assertFalse((self.root/"escaped").exists())

    def test_hardlinked_input_is_refused(self):
        path=self.root/"fixture";path.write_bytes(b"public")
        os.link(path,self.root/"another")
        with self.assertRaises(c.CapacityError):
            io.read_file(path)

    def test_read_size_and_type_bounds(self):
        path=self.root/"fixture";path.write_bytes(b"public")
        for bound in (True,0,-1,5,c.MAX_FILE_BYTES+1):
            with self.assertRaises(c.CapacityError):
                io.read_file(path,bound)
        with self.assertRaises(c.CapacityError):
            io.read_file(self.root)

    def test_write_requires_bounded_exact_bytes(self):
        for value in ("public",bytearray(b"public"),object()):
            with self.assertRaises(c.CapacityError):
                io.exclusive_write(self.root/"never",value)
            self.assertFalse((self.root/"never").exists())

    def test_fsync_failure_preserves_file_but_does_not_claim_success(self):
        with patch.object(io.os,"fsync",side_effect=OSError("PRIVATE-CANARY")):
            with self.assertRaises(c.CapacityError) as denied:
                io.exclusive_write(self.root/"new",b"public")
        self.assertNotIn("PRIVATE-CANARY",str(denied.exception))
        self.assertEqual((self.root/"new").read_bytes(),b"public")

    def test_file_identity_changed_during_open_refused(self):
        path=self.root/"fixture";path.write_bytes(b"public")
        original=io.os.open
        def replace(target,*args,**kwargs):
            path.rename(self.root/"old")
            path.write_bytes(b"public")
            return original(target,*args,**kwargs)
        with patch.object(io.os,"open",side_effect=replace):
            with self.assertRaises(c.CapacityError):
                io.read_file(path)

    def test_growth_during_read_refused(self):
        path=self.root/"fixture";path.write_bytes(b"public")
        original=io.os.fstat;calls=0
        def change(fd):
            nonlocal calls
            calls+=1
            if calls==2:
                path.write_bytes(b"public changed")
            return original(fd)
        with patch.object(io.os,"fstat",side_effect=change):
            with self.assertRaises(c.CapacityError):
                io.read_file(path)
