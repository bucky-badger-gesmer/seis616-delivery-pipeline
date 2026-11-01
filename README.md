# Software Delivery Pipeline with Manual Approval

SEIS 616 homework. `pipeline.yaml` is a CloudFormation template that builds an automated delivery pipeline from GitHub, CodePipeline, and CodeBuild, with a **manual review stage**. When code is pushed to `main`, the pipeline pulls it, pauses, and emails the maintainer. It builds only after the maintainer approves. A rejected change never reaches the build.

The pipeline builds the small Python app in this repo (`rectangle/`): it runs the pytest suite and packages the app as a single runnable file, `rectangle.pyz`.

```
git push (main)
  │  GitHub connection (CodeConnections)
  ▼
Source ──► Approval (manual) ──► Build (CodeBuild)
              │ SNS email to the maintainer   │ pytest, then zipapp
              │ waits for approve or reject   ▼
              ▼ reject stops the run          S3 artifact bucket: rectangle.pyz
```

## What's in this repo

| File                   | Purpose                                                                                                         |
| ---------------------- | --------------------------------------------------------------------------------------------------------------- |
| `pipeline.yaml`        | The CloudFormation template (the deliverable)                                                                   |
| `buildspec.yml`        | CodeBuild steps: install Python 3.12 and pytest, run the tests, package `rectangle.pyz`, run it once as a check |
| `rectangle/`           | The app: `area`, `perimeter`, and `diagonal` of a rectangle, plus a command-line entry point                    |
| `tests/`               | pytest tests                                                                                                    |
| `requirements-dev.txt` | pytest, the only dependency                                                                                     |

## What the template creates

| Resource         | Type                          | Role in the pipeline                                                                                   |
| ---------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------ |
| `ArtifactBucket` | `AWS::S3::Bucket`             | Holds the source and build artifacts passed between stages (encrypted, no public access)               |
| `ApprovalTopic`  | `AWS::SNS::Topic`             | Emails the maintainer (`MaintainerEmail`) when a change is waiting for review                          |
| `CodeBuildRole`  | `AWS::IAM::Role`              | Lets CodeBuild write its logs, read and write artifacts, and publish test reports, and nothing else    |
| `BuildProject`   | `AWS::CodeBuild::Project`     | Runs `buildspec.yml` on the Amazon Linux standard 5.0 image                                            |
| `PipelineRole`   | `AWS::IAM::Role`              | Lets CodePipeline use the GitHub connection, the artifact bucket, the build project, and the SNS topic |
| `Pipeline`       | `AWS::CodePipeline::Pipeline` | Three stages: **Source** → **Approval** (`MaintainerReview`) → **Build** (`TestAndPackage`)            |

Details worth knowing:

- **The approval stage comes right after Source,** so nothing is built until a person has reviewed the change. The email includes the commit ID, the commit message, and a link to the commit on GitHub.
- **Pushes to `main` start the pipeline automatically.** Pushes that change only `README.md` or `docs/` are ignored, so editing documentation doesn't create a run that waits for approval.
- **GitHub access uses a CodeConnections connection** (the AWS Connector GitHub App), so no personal access token is stored anywhere.

## 1. Deploy the template

You need a CodeConnections connection to GitHub in status **Available** (Developer Tools console → **Settings → Connections**).

| Parameter         | Value                                                                           |
| ----------------- | ------------------------------------------------------------------------------- |
| `ConnectionArn`   | The connection's ARN                                                            |
| `RepositoryId`    | `owner/repo` to build. Default: `bucky-badger-gesmer/seis616-delivery-pipeline` |
| `BranchName`      | Default: `main`                                                                 |
| `MaintainerEmail` | Who gets the review emails                                                      |

```
aws cloudformation create-stack --region us-east-1 \
  --stack-name seis616-pipeline \
  --template-body file://pipeline.yaml \
  --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=ConnectionArn,ParameterValue=<connection ARN> \
               ParameterKey=MaintainerEmail,ParameterValue=<your email>
aws cloudformation wait stack-create-complete --region us-east-1 --stack-name seis616-pipeline
```

`CAPABILITY_IAM` is required because the template creates two IAM roles. In the console, tick the IAM acknowledgement on the last page.

Then open the **"AWS Notification - Subscription Confirmation"** email and click **Confirm subscription**. Until you do, approval emails aren't delivered.

## 2. Review a change

1. Push a commit to `main`. The pipeline starts and stops at **Approval**.
2. The maintainer gets an **"APPROVAL NEEDED"** email with the commit details and a link to the review page.
3. In the CodePipeline console, click **Review** on the Approval stage, then **Approve** or **Reject**. Or from the CLI:

   ```
   aws codepipeline get-pipeline-state --name seis616-pipeline \
     --query 'stageStates[?stageName==`Approval`].actionStates[0].latestExecution.token' --output text
   aws codepipeline put-approval-result --pipeline-name seis616-pipeline \
     --stage-name Approval --action-name MaintainerReview --token <token> \
     --result summary='Looks good',status=Approved
   ```

4. **Approved:** the Build stage runs the tests and stores `rectangle.pyz` in the artifact bucket. **Rejected:** the run stops as `Failed` and Build never runs.

## How I verified it

I deployed the template from its GitHub copy as stack `seis616-pipeline` in us-east-1 and tested both outcomes of the review stage. The outputs below are trimmed; full command output is in my verification log.

### Stack created

`CREATE_COMPLETE` on the first attempt, with all six resources:

```
$ aws cloudformation describe-stack-resources --stack-name seis616-pipeline \
    --query 'StackResources[].[LogicalResourceId,ResourceType,ResourceStatus]' --output table
|  ApprovalTopic |  AWS::SNS::Topic              |  CREATE_COMPLETE  |
|  ArtifactBucket|  AWS::S3::Bucket              |  CREATE_COMPLETE  |
|  BuildProject  |  AWS::CodeBuild::Project      |  CREATE_COMPLETE  |
|  CodeBuildRole |  AWS::IAM::Role               |  CREATE_COMPLETE  |
|  Pipeline      |  AWS::CodePipeline::Pipeline  |  CREATE_COMPLETE  |
|  PipelineRole  |  AWS::IAM::Role               |  CREATE_COMPLETE  |
```

### Test 1: a rejected change never builds

Creating the pipeline starts a run on the latest commit. It stopped at Approval with Build untouched:

```
$ aws codepipeline get-pipeline-state --name seis616-pipeline \
    --query 'stageStates[].{stage:stageName,status:latestExecution.status}' --output table
|  Source   |  Succeeded   |
|  Approval |  InProgress  |
|  Build    |  None        |
```

The review request carries the commit details, filled in from the Source stage:

```
"CustomData": "Review commit 192d80e82423ad8035dc16330deca35b8bdfc0df: feat: add rectangle app, buildspec, and delivery pipeline template ...",
"ExternalEntityLink": "https://github.com/bucky-badger-gesmer/seis616-delivery-pipeline/commit/192d80e82423ad8035dc16330deca35b8bdfc0df"
```

I rejected it. The run ended as `Failed`, and the build project has no builds at all:

```
$ aws codepipeline put-approval-result --pipeline-name seis616-pipeline --stage-name Approval \
    --action-name MaintainerReview --token <token> \
    --result summary='Rejected for verification: reject path test',status=Rejected
$ aws codepipeline get-pipeline-state --name seis616-pipeline ...
|  Source  |  Succeeded |
|  Approval|  Failed    |  Rejected for verification: reject path test
|  Build   |  None      |
$ aws codebuild list-builds-for-project --project-name seis616-pipeline-build
{ "ids": [] }
```

### Test 2: an approved change builds

After confirming the email subscription, I pushed a code change (`6fbc395`, adds `diagonal()` and its test). GitHub's webhook started a new run, which paused at Approval:

```
$ aws codepipeline list-pipeline-executions --pipeline-name seis616-pipeline ...
|  e460dcae-ee18-43e8-a252-b04d85fd83cb |  InProgress |  WebhookV2      |  6fbc395634461cc301252b8866b85a2ffcb6e274  |
|  acb33a38-11aa-4a5c-95b3-7b1565ddfe27 |  Failed     |  CreatePipeline |  192d80e82423ad8035dc16330deca35b8bdfc0df  |
```

The **"APPROVAL NEEDED"** email arrived at the maintainer address. SNS reports every message delivered:

```
NumberOfMessagesPublished: 2.0
NumberOfNotificationsDelivered: 2.0
NumberOfNotificationsFailed: 0.0
```

I approved it in the console. The pipeline resumed and the build succeeded:

```
$ aws codepipeline list-action-executions --pipeline-name seis616-pipeline --filter pipelineExecutionId=e460dcae-... ...
|  TestAndPackage  |  Succeeded |
|  MaintainerReview|  Succeeded |  Approved by arn:aws:iam::762760349846:user/aaron
|  Source          |  Succeeded |
```

Build log, showing Python 3.12 and all tests passing:

```
platform linux -- Python 3.12.15, pytest-8.4.2, pluggy-1.7.0
tests/test_rectangle.py::test_area PASSED
tests/test_rectangle.py::test_perimeter PASSED
tests/test_rectangle.py::test_diagonal PASSED
tests/test_rectangle.py::test_zero_sides PASSED
tests/test_rectangle.py::test_negative_side_rejected PASSED
============================== 5 passed in 0.02s ===============================
area=12.0 perimeter=14.0 diagonal=5.0
```

CodeBuild's test report agrees: 5 succeeded, 0 failed. Finally, I downloaded the build artifact from the pipeline's S3 bucket and ran it:

```
$ aws s3 cp s3://<artifact bucket>/seis616-pipeline/BuildOutpu/UCmUX5e build-output.zip
$ unzip build-output.zip && python3 rectangle.pyz 3 4
area=12.0 perimeter=14.0 diagonal=5.0
```

### Test 3: documentation-only pushes don't start a run

I pushed this README by itself (`6db9308`, only `README.md` changed). No new run appeared. The list still shows just the two runs above:

```
$ aws codepipeline list-pipeline-executions --pipeline-name seis616-pipeline ...
|  e460dcae-ee18-43e8-a252-b04d85fd83cb |  Succeeded |  WebhookV2      |  6fbc395634461cc301252b8866b85a2ffcb6e274  |
|  acb33a38-11aa-4a5c-95b3-7b1565ddfe27 |  Failed    |  CreatePipeline |  192d80e82423ad8035dc16330deca35b8bdfc0df  |
```

## 3. Tear it down

The stack can't delete a bucket that still holds artifacts, and CodeBuild creates a log group and a test report group that the stack doesn't own. Remove all of them:

```
BUCKET=$(aws cloudformation describe-stacks --stack-name seis616-pipeline \
  --query 'Stacks[0].Outputs[?OutputKey==`ArtifactBucketName`].OutputValue' --output text)
aws s3 rm s3://$BUCKET --recursive
aws cloudformation delete-stack --stack-name seis616-pipeline
aws cloudformation wait stack-delete-complete --stack-name seis616-pipeline
aws codebuild delete-report-group --delete-reports \
  --arn arn:aws:codebuild:us-east-1:<account>:report-group/seis616-pipeline-build-pytest-reports
aws logs delete-log-group --log-group-name /aws/codebuild/seis616-pipeline-build
```

Deleting the topic doesn't always remove its email subscription right away. If `aws sns list-subscriptions` still shows it, remove it with `aws sns unsubscribe`.

### How I verified the teardown

After running the commands above, a sweep of the account found nothing left from this project:

```
-- live stacks:
-- pipelines:
-- codebuild projects:
-- report groups:         0 (after they finished DELETING)
-- /aws/codebuild log groups:
-- SNS topics:
-- SNS subscriptions:     0 (after unsubscribing)
-- IAM roles matching pipeline/codebuild:
```

`seis616-pipeline` shows `DELETE_COMPLETE`. The only thing I kept is the GitHub connection, which is free and reusable.
