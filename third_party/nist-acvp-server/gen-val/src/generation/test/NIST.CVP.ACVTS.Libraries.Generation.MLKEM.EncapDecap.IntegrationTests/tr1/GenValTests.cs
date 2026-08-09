using NIST.CVP.ACVTS.Libraries.Common;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.Enums;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.MLKEM;
using NIST.CVP.ACVTS.Libraries.Generation.ML_KEM.FIPS203.tr1.EncapDecap;
using NIST.CVP.ACVTS.Libraries.Generation.Tests;
using NIST.CVP.ACVTS.Libraries.Math;
using NIST.CVP.ACVTS.Tests.Core.TestCategoryAttributes;
using NUnit.Framework;

namespace NIST.CVP.ACVTS.Libraries.Generation.MLKEM.EncapDecap.IntegrationTests.tr1;

[TestFixture, FastIntegrationTest]
public class GenValTests : GenValTestsSingleRunnerBase
{
    public override string Algorithm { get; } = "ML-KEM";
    public override string Mode { get; } = "encapDecap";
    public override string Revision { get; set; } = "FIPS203-tr1";
    
    public override AlgoMode AlgoMode => AlgoMode.ML_KEM_EncapDecap_FIPS203_tr1;

    public override IRegisterInjections RegistrationsGenVal => new RegisterInjections();

    protected override void ModifyTestCaseToFail(dynamic testCase)
    {
        var rand = new Random800_90();

        if (testCase.k != null)
        {
            var bs = new BitString(testCase.k.ToString());
            bs = rand.GetDifferentBitStringOfSameSize(bs);
            testCase.k = bs.ToHex();
        }
        
        if (testCase.c != null)
        {
            var bs = new BitString(testCase.c.ToString());
            bs = rand.GetDifferentBitStringOfSameSize(bs);
            testCase.c = bs.ToHex();    
        }
        
        if (testCase.testPassed != null)
        {
            testCase.testPassed = testCase.testPassed != true;
        }
    }

    protected override string GetTestFileFewTestCases(string targetFolder)
    {
        var p = new Parameters
        {
            VectorSetId = 42,
            Algorithm = Algorithm,
            Mode = Mode,
            Revision = Revision,
            ParameterSets = [MLKEMParameterSet.ML_KEM_512],
            Functions = [MLKEMFunction.Encapsulation, MLKEMFunction.Decapsulation, MLKEMFunction.EncapsulationKeyCheck, MLKEMFunction.DecapsulationKeyCheck],
            KeyFormats = [PrivateKeyFormat.Seed, PrivateKeyFormat.Expanded],
            IsSample = true
        };

        return CreateRegistration(targetFolder, p);
    }

    protected override string GetTestFileLotsOfTestCases(string targetFolder)
    {
        var p = new Parameters
        {
            VectorSetId = 42,
            Algorithm = Algorithm,
            Mode = Mode,
            Revision = Revision,
            ParameterSets = ParameterValidator.VALID_PARAMETER_SETS,
            Functions = [MLKEMFunction.Encapsulation, MLKEMFunction.Decapsulation, MLKEMFunction.EncapsulationKeyCheck, MLKEMFunction.DecapsulationKeyCheck],
            KeyFormats = [PrivateKeyFormat.Seed, PrivateKeyFormat.Expanded],
            IsSample = true
        };

        return CreateRegistration(targetFolder, p);
    }
}
